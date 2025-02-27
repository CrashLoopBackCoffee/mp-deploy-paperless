"""Paperless ng."""

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

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
    opts=p.ResourceOptions.merge(
        k8s_opts,
        # protect namespace as the PVCs with the storage data are keeping track of the PVs,
        # otherwise new PVs are created:
        p.ResourceOptions(protect=True),
    ),
)

namespaced_provider = k8s.Provider(
    'paperless-provider',
    kubeconfig=kube_config,
    namespace=ns.metadata.name,
)
k8s_opts = p.ResourceOptions(provider=namespaced_provider)

REDIS_PORT = 6379
PAPERLESS_PORT = 8000

fqdn = p.Output.concat(p.get_project(), '.', k8s_stack.get_output('app-sub-domain'))
p.export('fqdn', fqdn)

admin_username = 'admin'
admin_password = random.RandomPassword('admin-password', length=64, special=False).result

p.export('admin-username', admin_username)
p.export('admin-password', admin_password)

config = k8s.core.v1.ConfigMap(
    'config',
    metadata={
        'name': 'config',
    },
    data={
        'PAPERLESS_REDIS': f'redis://localhost:{REDIS_PORT}',
        'PAPERLESS_URL': p.Output.concat('https://', fqdn),
        # https://docs.paperless-ngx.com/troubleshooting/#gunicorn-fails-to-start-with-is-not-a-valid-port-number
        'PAPERLESS_PORT': str(PAPERLESS_PORT),
        'PAPERLESS_ADMIN_USER': admin_username,
    },
    opts=k8s_opts,
)

config_secret = k8s.core.v1.Secret(
    'config-secret',
    metadata={
        'name': 'config-secret',
    },
    string_data={
        'PAPERLESS_SECRET_KEY': random.RandomPassword(
            'paperless-secret-key',
            length=64,
            special=False,
        ).result,
        'PAPERLESS_ADMIN_PASSWORD': admin_password,
    },
    type='Opaque',
    opts=k8s_opts,
)


sts = k8s.apps.v1.StatefulSet(
    'paperless',
    metadata={'name': 'paperless'},
    spec={
        'replicas': 1,
        'selector': {
            'match_labels': labels,
        },
        # we omit a headless service since we don't need cluster-internal network name identity:
        'service_name': '',
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
                                'container_port': PAPERLESS_PORT,
                            },
                        ],
                        'env_from': [
                            {
                                'config_map_ref': {
                                    'name': config.metadata.name,
                                }
                            },
                            {
                                'secret_ref': {
                                    'name': config_secret.metadata.name,
                                }
                            },
                        ],
                    },
                ],
            },
        },
        'volume_claim_templates': [
            {
                'metadata': {
                    'name': 'data',
                },
                'spec': {
                    'storage_class_name': 'data-hostpath-retained',
                    'access_modes': ['ReadWriteOnce'],
                    'resources': {'requests': {'storage': '1Gi'}},
                },
            },
            {
                'metadata': {
                    'name': 'media',
                },
                'spec': {
                    'storage_class_name': 'data-hostpath-retained',
                    'access_modes': ['ReadWriteOnce'],
                    'resources': {'requests': {'storage': '4Gi'}},
                },
            },
        ],
    },
    opts=k8s_opts,
)


service = k8s.core.v1.Service(
    'paperless',
    metadata={
        'name': 'paperless',
    },
    spec={
        'selector': sts.spec.selector.match_labels,
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
