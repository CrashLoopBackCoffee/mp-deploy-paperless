"""Paperless ng."""

import pulumi as p
import pulumi_kubernetes as k8s

from paperless.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().require_object('config'))

k8s_stack = p.StackReference(f'{p.get_organization()}/kubernetes/{p.get_stack()}')
kube_config = k8s_stack.get_output('kube-config')

k8s_provider = k8s.Provider('k8s', kubeconfig=kube_config)
k8s_opts = p.ResourceOptions(provider=k8s_provider)

labels = {'app': 'nginx'}

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

deployment = k8s.apps.v1.Deployment(
    'nginx',
    metadata={'name': 'nginx'},
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
                        'image': 'nginx',
                        'name': 'nginx',
                        'ports': [
                            {
                                'name': 'http',
                                'container_port': 80,
                            },
                        ],
                    }
                ],
            },
        },
    },
    opts=k8s_opts,
)

service = k8s.core.v1.Service(
    'nginx',
    metadata={
        'name': 'nginx',
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

fqdn = p.Output.concat(p.get_project(), '.', k8s_stack.get_output('app-sub-domain'))
p.export('fqdn', fqdn)

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
