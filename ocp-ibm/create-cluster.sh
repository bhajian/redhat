#!/bin/bash

# Designed to be run on the Red Hat OpenShift Installer host (Linux only)
# Can NOT be run on macOS, because of ccoctl binary

# Ensure pre-requisities are met before execution
# 1. IBM Cloud Private DNS instance and DNS Zone root domain (e.g. example.com)
# 2. Red Hat OpenShift Client CLI


# Ensure IBM Cloud CLI shell env var is defined for the IBM Cloud API Key
export IBMCLOUD_API_KEY="TVEp63mddpy5wOrJlYgCJ4RbN6Yl69ypKukPHaCjI7xG"
# Ensure Red Hat OpenShift shell env var is defined for the IBM Cloud API Key
export IC_API_KEY="$IBMCLOUD_API_KEY"

# Get the OpenShift Cluster Manager (OCM) API Offline Token using https://console.redhat.com/openshift/token
rh_ocp_cluster_mgr_offline_token="eyJhbGciOiJIUzUxMiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI0NzQzYTkzMC03YmJiLTRkZGQtOTgzMS00ODcxNGRlZDc0YjUifQ.eyJpYXQiOjE3NDQwNDc0MjUsImp0aSI6ImM2MWNiZWUzLWM1MDYtNDI0My1hNmI1LTU1Y2JiMjZjYzg2OCIsImlzcyI6Imh0dHBzOi8vc3NvLnJlZGhhdC5jb20vYXV0aC9yZWFsbXMvcmVkaGF0LWV4dGVybmFsIiwiYXVkIjoiaHR0cHM6Ly9zc28ucmVkaGF0LmNvbS9hdXRoL3JlYWxtcy9yZWRoYXQtZXh0ZXJuYWwiLCJzdWIiOiJmOjUyOGQ3NmZmLWY3MDgtNDNlZC04Y2Q1LWZlMTZmNGZlMGNlNjpyaG4tZ3BzLWJoYWppYW4iLCJ0eXAiOiJPZmZsaW5lIiwiYXpwIjoiY2xvdWQtc2VydmljZXMiLCJub25jZSI6IjIwNzVlYTE0LWQ2MDktNGU5OS1hMjRhLWY0ZjM3NTMxMmVjZSIsInNpZCI6ImIwMTY1YzEwLWZhYzItNDk1NS1hZjQzLWIyNTRkNDkyN2RiZSIsInNjb3BlIjoib3BlbmlkIGJhc2ljIGFwaS5pYW0uc2VydmljZV9hY2NvdW50cyByb2xlcyB3ZWItb3JpZ2lucyBjbGllbnRfdHlwZS5wcmVfa2MyNSBvZmZsaW5lX2FjY2VzcyJ9.DSJuegj1s46EpnobJj-gLxWM5SLjh456urelll55cIuuueJBo8nnBXVU2yK_4EpmZ6rgjJD6muj_x7TyEh9mOA"

# Define directories required during installation
ocp_installer_work_directory="$PWD/rhocp_prep"
ocp_installer_init_directory="$PWD/rhocp_init"

# Define location of SSH Private Key to use during deployment
ocp_cluster_hosts_private_key="/root/.ssh/hosts_rsa"

# Define Red Hat OpenShift cluster prefix for all resources
ocp_resource_prefix="ocp-test"

# Define target IBM Cloud Resource Group for all resources used for the Red Hat OpenShift
ibmcloud_target_rg="Default"


# Begin activities

# How to download the pull secret from cloud.redhat.com/openshift/install/pull-secret using a REST API call?
# https://access.redhat.com/solutions/4844461
export rh_ocp_cluster_mgr_session_access_token=$(curl \
https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token \
--silent \
--data-urlencode "grant_type=refresh_token" \
--data-urlencode "client_id=cloud-services" \
--data-urlencode "refresh_token=$rh_ocp_cluster_mgr_offline_token" \
| jq -r .access_token)


export rh_ocp_cluster_mgr_pull_secret=$(curl -X POST \
--silent \
https://api.openshift.com/api/accounts_mgmt/v1/access_token \
--header "Content-Type:application/json" \
--header "Authorization: Bearer $rh_ocp_cluster_mgr_session_access_token")


echo "Allow host of Red Hat OpenShift Installer to SSH into hosts deployed by IPI... (RH OCP Installer appears to exclusively use ssh-agent method)"
echo "Host 10.*" >> /etc/ssh/ssh_config
echo "    IdentityFile $ocp_cluster_hosts_private_key" >> /etc/ssh/ssh_config
echo "    StrictHostKeyChecking accept-new" >> /etc/ssh/ssh_config
chmod 400 $ocp_cluster_hosts_private_key
service ssh restart
# Force start auth via ssh-agent in current shell as background task
eval "$(ssh-agent)"
# Force start auth via ssh-agent in current shell as background task, force Bash shell
#eval "$(ssh-agent -s)"
# Show existing identities being managed by SSH Agent
ssh-add -l
# Add private key
ssh-add $ocp_cluster_hosts_private_key
# Show added identity managed by SSH Agent
ssh-add -l


# Create directories required during installation
mkdir -p $ocp_installer_work_directory/cli_tar
mkdir -p $ocp_installer_work_directory/cli_extracted
mkdir -p $ocp_installer_work_directory/installer_tar
mkdir -p $ocp_installer_work_directory/installer_extracted
mkdir -p $ocp_installer_work_directory/ccoctl_credentials_requests
mkdir -p $ocp_installer_init_directory


# Download, Extract and Install OpenShift Client CLI
curl -L -o $ocp_installer_work_directory/cli_tar/openshift-client-linux.tar.gz https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz
tar -xvf $ocp_installer_work_directory/cli_tar/openshift-client-linux.tar.gz -C $ocp_installer_work_directory/cli_extracted
mv --force $ocp_installer_work_directory/cli_extracted/oc /usr/local/bin
mv --force $ocp_installer_work_directory/cli_extracted/kubectl /usr/local/bin


# Download and Extract Red Hat OpenShift Installer
curl -o $ocp_installer_work_directory/installer_tar/openshift-install-linux.tar.gz https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-install-linux.tar.gz
tar -xvf $ocp_installer_work_directory/installer_tar/openshift-install-linux.tar.gz -C $ocp_installer_work_directory/installer_extracted


# OpenShift Container Platform (OCP) clusters, via installer-provisioned infrastructure (IPI)
# This installer will provision and configure the infrastructure for the OCP cluster


# Generate Ignition Install Config file (install-config.yaml)
# Interactive only, cannot automate!!!
# !!! BROKEN for IBM Cloud DNS Services (Private DNS), enforces usage of Public DNS Zone (via IBM Cloud Internet Services, powered by Cloudflare)
#$ocp_installer_work_directory/extracted/openshift-install create install-config --dir $ocp_installer_init_directory --log-level debug
echo "ALERT!!! BROKEN!!!"
echo "Should run...."
echo "$ocp_installer_work_directory/extracted/openshift-install create install-config --dir $ocp_installer_init_directory --log-level debug"
echo ""
echo "This is an interactive only command, it cannot be automated."
echo "In addition, this is broken for IBM Cloud DNS Services (Private DNS), it enforces usage of Public DNS Zone (via IBM Cloud Internet Services, powered by Cloudflare)"
echo "Pausing script for 60 seconds in case end user copy/pasted without seeing this"
echo "Make sure the file $ocp_installer_init_directory/install-config.yaml already exists before continuing (and do not use .yml file extension)"
sleep 60


# Extract credentials requests YML to use with the Cloud Credential Operator (COO) utility
RELEASE_IMAGE=$($ocp_installer_work_directory/installer_extracted/openshift-install version | awk '/release image/ {print $3}')
oc adm release extract --cloud=ibmcloud --credentials-requests $RELEASE_IMAGE --to=$ocp_installer_work_directory/ccoctl_credentials_requests

# Extracting the Cloud Credential Operator (COO) utility
# ccoctl is a Linux binary that must run in a Linux environment
CCO_IMAGE=$(oc adm release info --image-for='cloud-credential-operator' $RELEASE_IMAGE --registry-config="$ocp_installer_work_directory/rh_ocp_cluster_mgr_pull_secret.txt")
oc image extract $CCO_IMAGE --path="/usr/bin/ccoctl:$ocp_installer_work_directory" --confirm --registry-config="$ocp_installer_work_directory/rh_ocp_cluster_mgr_pull_secret.txt"
chmod 775 $ocp_installer_work_directory/ccoctl

# Configuring the Cloud Credential Operator (COO) utility
# ccoctl is a Linux binary that must run in a Linux environment, and requires either IC_API_KEY IBMCLOUD_API_KEY env var to be set
# The ccoctl credentials request files must be extracted to a separate directory, otherwise will cause errors such as 'Error: Failed to validate the serviceID: Spec.ProviderSpec is empty in credentials request'
# Subsequent credentials configuration files will be saved to the /manifests directory
# The IBM Cloud IAM Service IDs will be created afterwards, if there are duplicate names then it will show 'Error: Failed to validate the serviceID: exists with the same name: please delete the entries or create with a different name'
$ocp_installer_work_directory/ccoctl ibmcloud create-service-id \
--credentials-requests-dir $ocp_installer_work_directory/ccoctl_credentials_requests \
--name $ocp_resource_prefix-cluster \
--output-dir $ocp_installer_init_directory \
--resource-group-name $ibmcloud_target_rg

# Perform final generation of credentials configuration files (Kubernetes Manifests) will be saved to the /manifests directory, via Ignition
# install-config.yaml MUST have 'a' and not use file extension .yml otherwise interactive mode will start
echo "Run Red Hat OpenShift Installer to create final credentials configurations file to /manifests directory"
echo "NOTE: Must find install-config.yaml otherwise will default to interactive mode"
$ocp_installer_work_directory/installer_extracted/openshift-install create manifests --dir $ocp_installer_init_directory --log-level debug

echo "Created IBM Cloud IAM Service IDs..."
echo "These would need to be manually removed if reinstalling...."
echo "Examples of IBM Cloud IAM Service IDs created:"
echo "CLUSTER_NAME-openshift-machine-api-ibmcloud-credentials"
echo "CLUSTER_NAME-openshift-ingress-operator-cloud-credentials"
echo "CLUSTER_NAME-openshift-image-registry-installer-cloud-credentials"
echo "CLUSTER_NAME-openshift-cluster-csi-drivers-ibm-cloud-credentials"
echo "CLUSTER_NAME-openshift-cloud-controller-manager-ibm-cloud-credentials"


# Perform installation, via Ignition, to create the Bootstrap node, Control plane, Compute node/s
# install-config.yaml MUST have 'a' and not use file extension .yml otherwise interactive mode will start
echo "Run Red Hat OpenShift Installer to create the OCP Cluster. These resources would need to be manually removed if reinstalling...."
echo "NOTE: Must find install-config.yaml otherwise will default to interactive mode"
$ocp_installer_work_directory/installer_extracted/openshift-install create cluster --dir $ocp_installer_init_directory --log-level debug


# DEBUG: Check Ports open connectivity after OCP Installer
#yum --assumeyes --debuglevel=1 install nc
### Check TCP
#nc host port
#nc -v -z -w 5 api.sapocp-cluster.$dns_root_domain 6443
#nc -v -z -w 5 api-int.sapocp-cluster.$dns_root_domain 6443
### Check UDP
#nc host port -u
#nc -v -z -w 5 -u api.sapocp-cluster.$dns_root_domain 6443
#nc -v -z -w 5 -u api-int.sapocp-cluster.$dns_root_domain 6443


# The Cloud Credential Operator (CCO) utility ccoctl supports updating secrets for clusters installed on IBM Cloud.
#$ocp_installer_work_directory/ccoctl ibmcloud refresh-keys \
#--kubeconfig <openshift_kubeconfig_file> \
#--credentials-requests-dir <path_to_credential_requests_directory> \
#--name <name>


# Post-install: Get status of all OCP cluster worker nodes
export KUBECONFIG=$ocp_installer_init_directory/auth/kubeconfig
oc get nodes

# Post-install: Get installation output as variables
ocp_cluster_web_console=$(oc whoami --show-console)
ocp_cluster_user=$(grep 'Login to the console with user:' $ocp_installer_init_directory/.openshift_install.log | sed 's|.*user:||' | awk '{ print $1 }' | sed 's|\\"||g' | sed 's/.$//')
ocp_cluster_user_password=$(grep 'Login to the console with user:' $ocp_installer_init_directory/.openshift_install.log | sed 's|.*user:||' | awk '{ print $4 }' | sed 's|\\"||g' | sed 's/.$//')