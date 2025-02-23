"""Paperless ng."""

import pulumi as p
import pulumi_kubernetes as k8s

from paperless.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().require_object('config'))

k8s_stack = p.StackReference(f'{p.get_organization()}/kubernetes/{p.get_stack()}')
kube_config = k8s_stack.get_output('kube-config')

k8s_provider = k8s.Provider('k8s', kubeconfig=kube_config)
k8s_opts = p.ResourceOptions(provider=k8s_provider)

labels = {'app': 'paperless'}

ns = k8s.core.v1.Namespace(
    'paperless',
    metadata={'name': 'paperless'},
    opts=p.ResourceOptions(provider=k8s_provider),
)

namespaced_provider = k8s.Provider(
    'paperless-provider',
    kubeconfig=kube_config,
    namespace=ns.metadata.name,
)
k8s_opts = p.ResourceOptions(provider=namespaced_provider)

REDIS_PORT = 6379

fqdn = p.Output.concat(p.get_project(), '.', k8s_stack.get_output('app-sub-domain'))
p.export('fqdn', fqdn)

data_pvc = k8s.core.v1.PersistentVolumeClaim(
    'data',
    metadata={
        'name': 'data',
    },
    spec={
        'storage_class_name': 'data-hostpath-retained',
        'access_modes': ['ReadWriteOnce'],
        'resources': {'requests': {'storage': '1Gi'}},
    },
    opts=k8s_opts,
)

media_pvc = k8s.core.v1.PersistentVolumeClaim(
    'media',
    metadata={
        'name': 'media',
    },
    spec={
        'storage_class_name': 'data-hostpath-retained',
        'access_modes': ['ReadWriteOnce'],
        'resources': {'requests': {'storage': '4Gi'}},
    },
    opts=k8s_opts,
)

deployment = k8s.apps.v1.Deployment(
    'paperless',
    metadata={'name': 'paperless'},
    spec={
        'replicas': 1,
        'selector': {
            'match_labels': labels,
        },
        'template': {
            'metadata': {
                'labels': labels,
            },
            'spec': {
                'containers': [
                    {
                        'name': 'broker',
                        'image': 'docker.io/library/redis:7',
                        'ports': [
                            {
                                'name': 'redis',
                                'container_port': REDIS_PORT,
                            },
                        ],
                    },
                    {
                        'name': 'webserver',
                        'image': 'ghcr.io/paperless-ngx/paperless-ngx:latest',
                        'volume_mounts': [
                            {
                                'name': 'data',
                                'mount_path': '/usr/src/paperless/data',
                            },
                            {
                                'name': 'media',
                                'mount_path': '/usr/src/paperless/media',
                            },
                        ],
                        'ports': [
                            {
                                'name': 'http',
                                'container_port': 8000,
                            },
                        ],
                        'env': [
                            {
                                'name': 'PAPERLESS_REDIS',
                                'value': f'redis://localhost:{REDIS_PORT}',
                            },
                            {
                                'name': 'PAPERLESS_URL',
                                'value': p.Output.concat('https://', fqdn),
                            },
                        ],
                    },
                ],
                'volumes': [
                    {
                        'name': 'data',
                        'persistent_volume_claim': {
                            'claim_name': data_pvc.metadata.name,
                        },
                    },
                    {
                        'name': 'media',
                        'persistent_volume_claim': {
                            'claim_name': media_pvc.metadata.name,
                        },
                    },
                ],
            },
        },
    },
    opts=k8s_opts,
)

service = k8s.core.v1.Service(
    'paperless',
    metadata={
        'name': 'paperless',
    },
    spec={
        'selector': deployment.spec.selector.match_labels,
        'ports': [
            {
                'name': 'http',
                'port': 80,
                'target_port': 'http',
            },
        ],
    },
    opts=k8s_opts,
)


ingress = k8s.apiextensions.CustomResource(
    'ingress',
    api_version='traefik.io/v1alpha1',
    kind='IngressRoute',
    metadata={
        'name': 'ingress',
    },
    spec={
        'entryPoints': ['websecure'],
        'routes': [
            {
                'kind': 'Rule',
                'match': p.Output.concat('Host(`', fqdn, '`)'),
                'services': [
                    {
                        'name': service.metadata.name,
                        'namespace': service.metadata.namespace,
                        'port': 'http',
                    },
                ],
            }
        ],
        # use default wildcard certificate:
        'tls': {},
    },
    opts=k8s_opts,
)
