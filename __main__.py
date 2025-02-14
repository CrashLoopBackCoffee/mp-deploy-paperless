"""Paperless ng."""

import os

import pulumi as p
import pulumi_kubernetes as k8s

from mp.deploy_utils import unify

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

nginx_config = k8s.core.v1.ConfigMap(
    'nginx-config',
    data={
        'nginx.conf': """
            events {}
            http {
                server {
                    listen 443 ssl;
                    ssl_certificate /etc/nginx/ssl/tls.crt;
                    ssl_certificate_key /etc/nginx/ssl/tls.key;
                    location / {
                        root /usr/share/nginx/html;
                        index index.html;
                    }
                }
            }
        """,
    },
    opts=k8s_opts,
)

certificate = k8s.apiextensions.CustomResource(
    'certificate',
    api_version='cert-manager.io/v1',
    kind='Certificate',
    metadata={
        'name': 'certificate',
        'annotations': {
            # wait for certificate to be issued before starting deployment (and hence application
            # containers):
            'pulumi.com/waitFor': 'condition=Ready',
        },
    },
    spec={
        'secretName': 'certificate',
        'dnsNames': [component_config.service.domain_name],
        'issuerRef': {
            'kind': 'ClusterIssuer',
            'name': 'lets-encrypt',
        },
    },
    opts=k8s_opts,
)

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
                            # {
                            #     'container_port': 443,
                            # },
                        ],
                        # 'volume_mounts': [
                        #     {
                        #         'name': 'nginx-config',
                        #         'mount_path': '/etc/nginx/nginx.conf',
                        #         'sub_path': 'nginx.conf',
                        #     },
                        #     {
                        #         'name': 'nginx-tls',
                        #         'mount_path': '/etc/nginx/ssl',
                        #     },
                        # ],
                    }
                ],
                # 'volumes': [
                #     {
                #         'name': 'nginx-config',
                #         'config_map': {
                #             'name': nginx_config.metadata.name,
                #         },
                #     },
                #     {
                #         'name': 'nginx-tls',
                #         'secret': {
                #             'secret_name': certificate.spec['secretName'],  # pyright: ignore[reportAttributeAccessIssue]  # custom resource attribute unknown
                #         },
                #     },
                # ],
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
            # {
            #     'name': 'https',
            #     'port': 443,
            #     'target_port': 443,
            # },
            {
                'name': 'http',
                'port': 80,
                'target_port': 'http',
            },
        ],
        # 'type': 'LoadBalancer',
    },
    opts=k8s_opts,
)

# ingress = k8s.networking.v1.Ingress(
#     'ingress',
#     metadata={'name': 'ingress'},
#     spec={
#         'rules': [
#             {
#                 'http': {
#                     'paths': [
#                         {
#                             'path': '/',
#                             'path_type': 'Prefix',
#                             'backend': {
#                                 'service': {
#                                     'name': service.metadata.name,
#                                     'port': {
#                                         'name': 'http',
#                                     },
#                                 }
#                             },
#                         }
#                     ]
#                 }
#             }
#         ]
#     },
#     opts=k8s_opts,
# )

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
                'match': f'Host(`{component_config.service.domain_name}`)',
                'kind': 'Rule',
                'services': [
                    {
                        'name': service.metadata.name,
                        'namespace': service.metadata.namespace,
                        'port': 'http',
                    },
                ],
            }
        ],
        'tls': {'secretName': certificate.spec['secretName']},  # pyright: ignore[reportAttributeAccessIssue]
    },
    opts=k8s_opts,
)

# ipv4 = service.status.load_balancer.ingress[0].ip
# TODO take from kubernetes or even set up whitelist dns entry right there:
ipv4 = '10.0.10.116'
# p.export('ipv4', ipv4)

dns_provider = unify.UnifyDnsRecordProvider(
    base_url=str(component_config.unify.url),
    api_token=os.environ['UNIFY_API_TOKEN__PULUMI'],
    verify_ssl=component_config.unify.verify_ssl,
)

unify.UnifyDnsRecord(
    'dns',
    domain_name=component_config.service.domain_name,
    ipv4=ipv4,
    provider=dns_provider,
)
