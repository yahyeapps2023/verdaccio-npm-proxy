#!/usr/bin/env python3
"""
Process Kubernetes deployment templates with app_info injections.

Reads app_info JSON, locates or creates deployments.yml, processes
placeholders, and injects secrets, vars, and storage configuration.
"""

import json
import os
import sys
import yaml

 

 

def get_field(app_info, *keys):
    for key in keys:
        if key in app_info:
            return app_info[key]
    return None


def parse_env_entries(app_info):
    """Parse `ENV` (or `env`) from app_info into secrets list.

    Expects ENV to be a dict object with key/value pairs.
    Example: app_info.ENV.DB_URL returns a value directly.
    Returns a list of dicts with 'name' and 'value' keys.
    """
    env_raw = get_field(app_info, 'ENV', 'env')
    secrets_list = []
    
    if not env_raw:
        return secrets_list

    if isinstance(env_raw, dict):
        for key, value in env_raw.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            secrets_list.append({'name': str(key), 'value': str(value)})

    return secrets_list

 

def replace_placeholders(content, app_info):
    """Replace template placeholders with values from app_info."""
    ns = get_field(app_info, 'namespace', 'NAMESPACE') or 'default'
    hostname = get_field(app_info, 'hostname', 'HOSTNAME') or 'example.com'
    image = get_field(app_info, 'image', 'IMAGE') or 'localhost:5000/app:latest'
    
    content = content.replace('{{NAMESPACE}}', ns)
    content = content.replace('{{HOSTNAME}}', hostname)
    content = content.replace('{{IMAGE}}', image)
    
    return content


def inject_secrets(docs, app_info):
    """Inject secrets into a Kubernetes Secret document."""
    secrets = parse_env_entries(app_info) or []
    if not secrets:
        return

    # Find an existing Secret resource, or create one.
    secret_doc = None
    for doc in docs:
        if isinstance(doc, dict) and doc.get('kind') == 'Secret' and doc.get('metadata', {}).get('name') == 'webhook-secrets':
            secret_doc = doc
            break

    if secret_doc is None:
        secret_doc = {
            'apiVersion': 'v1',
            'kind': 'Secret',
            'metadata': {
                'name': 'webhook-secrets',
                'namespace': get_field(app_info, 'namespace', 'NAMESPACE') or 'default'
            },
            'type': 'Opaque',
            'stringData': {}
        }
        docs.append(secret_doc)

    string_data = secret_doc.get('stringData')
    if string_data is None:
        string_data = {}
        secret_doc['stringData'] = string_data

    count = 0
    for s in secrets:
        name = s.get('name', '').strip()
        val = s.get('value', '').strip()
        if name and val:
            string_data[name] = val
            count += 1

    if count:
        print(f"Injected {count} secrets into Kubernetes Secret 'webhook-secrets'")


def remove_certificate_if_no_hostname(docs, app_info):
    """Remove Certificate and Ingress if HOSTNAME is not provided."""
    hostname = get_field(app_info, 'hostname', 'HOSTNAME')
    
    if hostname and hostname.strip():
        # HOSTNAME is available, keep Certificate and Ingress
        return
    
    # Remove Certificate and Ingress resources if no HOSTNAME
    docs_to_remove = []
    for i, doc in enumerate(docs):
        if isinstance(doc, dict):
            kind = doc.get('kind')
            if kind == 'Certificate':
                docs_to_remove.append(i)
                print("Removed Certificate resource (no HOSTNAME provided)")
            elif kind == 'Ingress':
                docs_to_remove.append(i)
                print("Removed Ingress resource (no HOSTNAME provided)")
    
    # Remove in reverse order to maintain indices
    for i in reversed(docs_to_remove):
        docs.pop(i)


def inject_deployment_env(docs, app_info):
    """Inject environment variable mappings into Deployment containers."""
    deployment_doc = None
    for doc in docs:
        if isinstance(doc, dict) and doc.get('kind') == 'Deployment':
            deployment_doc = doc
            break
    
    if not deployment_doc:
        return
    
    try:
        containers = deployment_doc['spec']['template']['spec']['containers']
        if not containers:
            return
        
        env = []
        
    
        # Add env from secrets (Secret refs)
        for s in parse_env_entries(app_info) or []:
            name = s.get('name', '').strip()
            if name:
                env.append({
                    'name': name,
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'webhook-secrets',
                            'key': name
                        }
                    }
                })
        
        if env:
            existing_env = containers[0].get('env', [])
            containers[0]['env'] = existing_env + env
            print(f"Injected {len(env)} environment mappings into Deployment")
    
    except Exception as e:
        print(f"WARNING: Could not inject env into Deployment: {e}")


def inject_storage(docs, app_info, namespace):
    """Inject storage configuration if provided in app_info."""
    storage = get_field(app_info, 'storage', 'STORAGE')
    if not storage:
        return
    
    # Find Deployment and patch volumes
    deployment_doc = None
    for doc in docs:
        if isinstance(doc, dict) and doc.get('kind') == 'Deployment':
            deployment_doc = doc
            break
    
    if not deployment_doc:
        print("WARNING: Storage requested but Deployment not found")
        return
    
    try:
        spec = deployment_doc['spec']['template']['spec']
        containers = spec.get('containers', [])
        
        if containers:
            # Add volumeMount to container
            vm = containers[0].setdefault('volumeMounts', [])
            vm.append({
                'name': 'app-storage',
                'mountPath': storage.get('mountPath', '/data')
            })
            
            # Add volume to pod spec
            vols = spec.setdefault('volumes', [])
            vols.append({
                'name': 'app-storage',
                'persistentVolumeClaim': {'claimName': 'app-pvc'}
            })
            
            print(f"Injected storage: {storage.get('size', '1Gi')} at {storage.get('mountPath', '/data')}")
    
    except Exception as e:
        print(f"WARNING: Could not patch storage into Deployment: {e}")
    
    # Create and append PVC document
    pvc = {
        'apiVersion': 'v1',
        'kind': 'PersistentVolumeClaim',
        'metadata': {
            'name': 'app-pvc',
            'namespace': namespace
        },
        'spec': {
            'accessModes': ['ReadWriteOnce'],
            'resources': {'requests': {'storage': storage.get('size', '1Gi')}},
            'storageClassName': storage.get('storageClassName', 'standard')
        }
    }
    docs.append(pvc)


def main():
    """Main entry point."""
    # Get paths from environment or arguments
    app_info = os.environ.get('APP_INFO')
    deploy_dir = os.environ.get('DEPLOY_DIR')
    deployment_template = os.environ.get('DEPLOYMENT_TEMPLATE')
    # parse app_info json
    try:
        app_info = json.loads(app_info)
    except Exception as e:
        print(f"ERROR: Failed to parse APP_INFO JSON: {e}")
        sys.exit(1)

 
    namespace = get_field(app_info, 'namespace', 'NAMESPACE') or 'default'
     
    # Load template
    with open(deployment_template, 'r') as f:
        content = f.read()
    
    # Replace placeholders
    content = replace_placeholders(content, app_info)
    
    # Parse YAML documents
    try:
        docs = list(yaml.safe_load_all(content))
    except Exception as e:
        print(f"ERROR: Failed to parse YAML template: {e}")
        sys.exit(1)
    
    # Inject data
    inject_secrets(docs, app_info)
    inject_deployment_env(docs, app_info)
    inject_storage(docs, app_info, namespace)
    remove_certificate_if_no_hostname(docs, app_info)
    
    # Write output to deploy/deployments.yml
    out_path = os.path.join(deploy_dir, 'deployments.yml')
    try:
        os.makedirs(deploy_dir, exist_ok=True)
        with open(out_path, 'w') as f:
            yaml.safe_dump_all(docs, f, default_flow_style=False, sort_keys=False)
        print(f"SUCCESS: Wrote deployments.yml to {out_path}")
    except Exception as e:
        print(f"ERROR: Failed to write deployments.yml: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
