"""Paperless ng."""

import pulumi as p
import pulumi_kubernetes as k8s

from paperless.app import create_paperless
from paperless.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().require_object('config'))

k8s_stack = p.StackReference(f'{p.get_organization()}/kubernetes/{p.get_stack()}')
kube_config = k8s_stack.get_output('kube-config')
k8s_provider = k8s.Provider('k8s', kubeconfig=kube_config)

fqdn = p.Output.concat(p.get_project(), '.', k8s_stack.get_output('app-sub-domain'))
p.export('fqdn', fqdn)

ns = k8s.core.v1.Namespace(
    'paperless',
    metadata={'name': 'paperless'},
    opts=p.ResourceOptions(
        provider=k8s_provider,
        # protect namespace as the PVCs with the storage data are keeping track of the PVs,
        # otherwise new PVs are created:
        protect=True,
    ),
)

namespaced_provider = k8s.Provider(
    'paperless-provider',
    kubeconfig=kube_config,
    namespace=ns.metadata.name,
)

create_paperless(component_config, fqdn, namespaced_provider)
