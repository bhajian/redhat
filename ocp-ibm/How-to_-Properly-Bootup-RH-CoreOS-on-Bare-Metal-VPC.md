
Fork from [pesa/kubevirt](https://github.ibm.com/pesa/kubevirt/wiki/How-to:-Properly-Bootup-RH-CoreOS-on-Bare-Metal-VPC)

## Creating the RH OCP cluster on IBM Cloud Virtual Servers (VPC)

```shell
#!/bin/bash

# Designed to be run on the Red Hat OpenShift Installer host (Linux only)
# Can NOT be run on macOS, because of ccoctl binary

# Ensure pre-requisities are met before execution
# 1. IBM Cloud Private DNS instance and DNS Zone root domain (e.g. example.com)
# 2. Red Hat OpenShift Client CLI


# Ensure IBM Cloud CLI shell env var is defined for the IBM Cloud API Key
export IBMCLOUD_API_KEY=""
# Ensure Red Hat OpenShift shell env var is defined for the IBM Cloud API Key
export IC_API_KEY="$IBMCLOUD_API_KEY"

# Get the OpenShift Cluster Manager (OCM) API Offline Token using https://console.redhat.com/openshift/token
rh_ocp_cluster_mgr_offline_token=""

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

```

## Preparing the RH OCP worker-user-data for the RHCOS Config URL

This process generates the RH OCP worker-user-data and uploads to a Private Access HTTP endpoint on IBM Cloud Object Storage (COS).

### Generate the RH OCP worker-user-data file

```shell
#!/bin/bash

# Designed to be run on the Red Hat OpenShift Installer host (Linux only)

# Shell variables - Required inputs
ibmcloud_api_key=""
ibmcloud_region=""
cos_instance_target=""
cos_bucket_target_region=""
target_bare_metal_hostname_short=""
ocp_installer_init_directory="$PWD/rhocp_init"

# Shell variables - Defaults
ocp_cluster_namespace="openshift-machine-api"
cos_bucket_target="rhcos-config-http1"
cos_endpoint_target="s3.$cos_bucket_target_region.cloud-object-storage.appdomain.cloud"
cos_endpoint_target_private="s3.direct.$cos_bucket_target_region.cloud-object-storage.appdomain.cloud"
cos_endpoint_target_private_https="s3-web.direct.$cos_bucket_target_region.cloud-object-storage.appdomain.cloud"
object_filename="$ocp_cluster_namespace-worker-user-data.ign"
target_bare_metal_hostname_short_base64=$(echo "$target_bare_metal_hostname_short" | base64)
target_bare_metal_data_payload="data:text/plain;charset=utf-8;base64,$target_bare_metal_hostname_short_base64"
rh_ocp_worker_userdata_file=$ocp_installer_init_directory/${target_bare_metal_hostname_short}.ign
rh_ocp_worker_userdata_temp=$ocp_installer_init_directory/${target_bare_metal_hostname_short}_tmp.ign
search_string="true"

# Check binaries available
if [ $(grep ^ID= /etc/os-release | cut -d '=' -f2 | tr -d '\"') = 'rhel' ]
then
  echo 'RHEL detected, running yum if necessary'
  if ! command -v ibmcloud &> /dev/null ; then curl -fsSL https://clis.cloud.ibm.com/install/linux | sh ; fi
  if ! command -v jq &> /dev/null ; then yum --assumeyes --debuglevel=1 install jq ; fi
  if ! command -v oc &> /dev/null
  then
    curl -L -o $ocp_installer_work_directory/cli_tar/openshift-client-linux.tar.gz https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz
    tar -xvf $ocp_installer_work_directory/cli_tar/openshift-client-linux.tar.gz -C $ocp_installer_work_directory/cli_extracted
    mv --force $ocp_installer_work_directory/cli_extracted/oc /usr/local/bin
    mv --force $ocp_installer_work_directory/cli_extracted/kubectl /usr/local/bin
  fi
fi

# Login to IBM Cloud CLI
ibmcloud login --apikey=$ibmcloud_api_key --no-region

# Install IBM Cloud CLI plugins
ibmcloud plugin install -f cloud-object-storage
ibmcloud plugin install -f vpc-infrastructure

# Identify CRN for given IBM Cloud Object Storage instance
cos_instance_crn=$(ibmcloud resource service-instance $cos_instance_target --quiet --output json | jq -r .[].crn)

# Create IBM Cloud Object Storage Bucket with HTTP Static Site and no Public Access, to an existing IBM Cloud Object Storage instance
ibmcloud cos bucket-create --bucket $cos_bucket_target --region $cos_bucket_target_region --class smart --ibm-service-instance-id $cos_instance_crn
ibmcloud cos bucket-website-put --bucket $cos_bucket_target --region $cos_bucket_target_region --website-configuration '{"ErrorDocument": {"Key": "error.html"},"IndexDocument": {"Suffix": "index.html"},"RoutingRules": [{"Condition": {"HttpErrorCodeReturnedEquals":"404"},"Redirect": {"HttpRedirectCode":"302","Protocol":"https","ReplaceKeyWith":"error404.html"}}]}'


# Load Kubeconfig file to Red Hat OpenShift Client CLI
export KUBECONFIG=$ocp_installer_init_directory/auth/kubeconfig

# Check default namespace is available
oc get namespace openshift-machine-api

# Extract Red Hat OpenShift worker user data file from the Red Hat OpenShift Client CLI
oc extract --namespace $ocp_cluster_namespace secret/worker-user-data --to=- > $rh_ocp_worker_userdata_file

# Loop through the lines of the worker user data file
while read line; do
  # Check if the line does not contain the search string
  if [[ $line != *"$search_string"* ]]; then
    # If not, add the line to the temporary file
    echo "$line" >> "$rh_ocp_worker_userdata_temp"
  fi
done < "$rh_ocp_worker_userdata_file"

# Parse
jq --compact-output --arg jq_var_source "$target_bare_metal_data_payload" '. + {"storage": {"files": [{"path": "/etc/hostname","mode": 420,"overwrite": true,"contents": {"source": $jq_var_source}}]}}' $rh_ocp_worker_userdata_temp > $object_filename
rm -f $rh_ocp_worker_userdata_temp
rm -f $rh_ocp_worker_userdata_file

# Login to IBM Cloud API endpoint and receive token
ibmcloud_api_key_access_token=$(curl --location --request POST "https://iam.cloud.ibm.com/identity/token" \
--header 'Content-Type: application/x-www-form-urlencoded' \
--header 'Accept: application/json' \
--data-urlencode 'grant_type=urn:ibm:params:oauth:grant-type:apikey' \
--data-urlencode "apikey=$ibmcloud_api_key" \
--data-urlencode 'response_type=cloud_iam' \
| jq -r .access_token)

# Upload Object to IBM Cloud Object Storage Bucket, using the header to allow anonymous user to read the file over HTTPS
curl -X "PUT" "https://$cos_endpoint_target/$cos_bucket_target/$object_filename" \
--header "Authorization: Bearer $ibmcloud_api_key_access_token" \
--header "x-amz-acl: public-read" \
--upload-file "$object_filename"

# Show HTTPS endpoint to use for RHCOS Config URL
echo "HTTPS endpoint for RHCOS Config URL... https://$cos_bucket_target.$cos_endpoint_target_private_https/$object_filename"


echo "Create new Security Group rule, for the Security Groups created by the Red Hat OpenShift Installer"
echo "Allow Bare Metal on VPC in the origin VPC Subnets, to connect to the Load Balancer etc."
ibmcloud target -r $ibmcloud_region
sg_kube_api_lb_name=$(ibmcloud is security-groups --quiet | grep sg-kube-api-lb | awk '{print $2}')
ibmcloud is security-group-rule-add $sg_kube_api_lb_name inbound tcp --port-min 22623 --port-max 22623 --remote 10.0.0.0/8
ibmcloud is security-group-rule-add $sg_kube_api_lb_name outbound tcp --port-min 22623 --port-max 22623 --remote 10.0.0.0/8

```


## Booting up Bare Metal on VPC to use RHCOS

This process walks you through the process of properly booting up a Bare Metal server with PCI NIC/s. Not following this process, you may encounter:
* Booting up on the wrong PCI NIC - unable to provision Bare Metal into OpenShift cluster due to connectivity failure
* Booting up server with incomplete domain search details

**NOTE**: Please see [issues](https://github.ibm.com/pesa/kubevirt/wiki/Issues-experienced-building-servers) page for known issues that you may run into.


### Ordering a Bare Metal to run RH CoreOS

For this example we've ordered a Bare Metal server with:
- 1..n PCI NIC/s
- 1 VLAN NIC - VLAN ID 100
- Profile: `bx2-metal-96x384`
- OS Image: `ibm-ubuntu-20-04-5-minimal-amd64-2`



### Bootstrap script for Bare Metal to run RH CoreOS

```shell
#!/bin/bash

# Designed to be run on Bare Metal (VPC) only

# Get vars from Shell Input
#IGN_URL="$1"
#RHCOS_RELEASE="$2"
#RHCOS_IMAGE_NAME="$3"

# Manual definition of vars
IGN_URL="https://rhcos-config-http1.s3-web.direct.us-south.cloud-object-storage.appdomain.cloud/NAMESPACE_HERE-worker-user-data.ign"
RHCOS_RELEASE="4.11"
RHCOS_IMAGE_NAME="rhcos-4.11.9-x86_64-metal.x86_64"

echo "### Confirmation required ###"
echo "Please note, this script will:"
echo "- download $RHCOS_IMAGE_NAME from Red Hat"
echo "- edit the RHCOS OS Image"
echo "- ERASE the boot disk of this Bare Metal"
echo "- write RHCOS OS Image to disk (/dev/sda)."
echo -e "###\n"
read -p "Press any key to continue..." -n1 -s
echo -e "\n"


echo "### Step 1. Install OS Packages"
if [ $(grep ^ID= /etc/os-release | cut -d '=' -f2 | tr -d '\"') = 'rhel' ]; then echo 'RHEL detected, running yum' && yum --assumeyes --debuglevel=1 install efibootmgr wget util-linux ipcalc ; fi
if [ $(grep ^ID= /etc/os-release | cut -d '=' -f2 | tr -d '\"') = 'ubuntu' ]; then echo 'Ubuntu detected, running apt-get' && apt-get --yes install efibootmgr wget fdisk ipcalc ; fi
if [ $(grep ^ID= /etc/os-release | cut -d '=' -f2 | tr -d '\"') = 'debian' ]; then echo 'Debian detected, running apt-get' && apt-get -y install efibootmgr wget fdisk ipcalc ; fi


echo "### Step 2. Get OS Network Interface settings"

# Detection of Primary Network Interface
# Find network adapter - identify the adapter, by showing which is used for the Default Gateway route
# If statement to catch RHEL installations with route table multiple default entries
# https://serverfault.com/questions/47915/how-do-i-get-the-default-gateway-in-linux-given-the-destination
if [[ $(ip route show default 0.0.0.0/0) == *$'\n'* ]]; then
    ACTIVE_NETWORK_ADAPTER=$(ip route show default 0.0.0.0/0 | awk '/default/ && !/metric/ {print $5}')
    ACTIVE_NETWORK_ADAPTER=${ACTIVE_NETWORK_ADAPTER%;*}
    ACTIVE_NETWORK_GATEWAY=$(ip route show default 0.0.0.0/0 | grep proto | awk '/default/ {print $3}')
else
    ACTIVE_NETWORK_ADAPTER=$(ip route show default 0.0.0.0/0 | awk '/default/ {print $5}')
    ACTIVE_NETWORK_GATEWAY=$(ip route show default 0.0.0.0/0 | awk '/default/ {print $3}')
fi
CURRENT_IP=$(ip -oneline address show $ACTIVE_NETWORK_ADAPTER | sed -n 's/.*inet \(.*\)\/.*/\1/p')
CURRENT_IP_CIDR=$(ip -oneline address show $ACTIVE_NETWORK_ADAPTER | sed -n 's/.*inet \(.*\) brd.*/\1/p')
CURRENT_IP_BRD=$(ip -oneline address show $ACTIVE_NETWORK_ADAPTER | sed -n 's/.*brd \(.*\) scope.*/\1/p')
CURRENT_IP_MASK=$(ipcalc $CURRENT_IP_CIDR -m --no-decorate | awk '{split($0,mask,"="); print mask[2]}')
CURRENT_HOSTNAME_SHORT=$(hostname -s)


echo "### Step 3. Show current disks and filesystems of this Bare Metal (for comparison with after 'dd' executed)"
fdisk -l /dev/sda


echo "### Step 4. Amend UEFI timeout to 5 seconds (default is 1 second)"
efibootmgr --timeout 5


echo "### Step 5. RHCOS OS Image preparations - Download RHCOS raw server image to Bare Metal host (and verify sha256 signature)"
wget "https://mirror.openshift.com/pub/openshift-v4/x86_64/dependencies/rhcos/$RHCOS_RELEASE/latest/$RHCOS_IMAGE_NAME.raw.gz"
wget "https://mirror.openshift.com/pub/openshift-v4/x86_64/dependencies/rhcos/$RHCOS_RELEASE/latest/sha256sum.txt"
grep "$RHCOS_IMAGE_NAME.raw.gz" sha256sum.txt | sha256sum --check


echo "### Step 6. RHCOS OS Image preparations - Extract RHCOS raw server image"
gunzip -d $RHCOS_IMAGE_NAME".raw.gz"


echo "### Step 7. RHCOS OS Image preparations - Attach RHCOS OS Image raw file to first available loop device"
losetup -f -P $PWD/$RHCOS_IMAGE_NAME.raw
sleep 5
LOOP=$(losetup -l | grep rhcos- | awk '{print $1}')
echo $LOOP


echo "### Step 8. RHCOS OS Image preparations - Mount RHCOS OS Image raw file /root partition to any directory"
mkdir -p $PWD/rhcos_mount
sleep 5
mount ${LOOP}p3 $PWD/rhcos_mount/


echo "### Step 9a. RHCOS OS Image preparations - Alter RHCOS OS Image raw file /loader/entries/ostree-1-rhcos.conf"
# On-the-fly SED to amend GRUB Boot Options line with RHCOS Ignition Config URL etc
# Append to end of the 'options' line, which will be appended to GRUB

# Ensure use of SED with delimiter pipe | when using URL
echo "Inject via sed, Ignition URL"
sed -i "3 s|$| ignition.config.url=$IGN_URL|" $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf

# Requirement for multiple NICs
echo "Inject via sed, multiple NICs"
sed -i "3 s/$/ rd.neednet=1/" $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf

# RHCOS uses ens1 as first network interface, therefore pass all details relevant to the Primary Network Interface of the Bare Metal
# If multiple entries for any variable, this will introduce a new line and cause error 'sed: -e expression #1, char 32: unterminated `s' command'
echo "Inject via sed, ip configuration"
sed -i "3 s/$/ ip=$CURRENT_IP::$ACTIVE_NETWORK_GATEWAY:$CURRENT_IP_MASK:$CURRENT_HOSTNAME_SHORT:ens1:none/" $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf

# Pass the DNS hosts
echo "Inject via sed, DNS hosts"
sed -i "3 s/$/ nameserver=161.26.0.7/" $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf
sed -i "3 s/$/ nameserver=161.26.0.8/" $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf


echo "### Step 9b. RHCOS OS Image preparations - Alter RHCOS OS Image raw file /grub2/grub.cfg"
# On-the-fly SED to amend GRUB Boot Options with increased GRUB Boot Loader timeout
sed -i "s/.*timeout=1.*/timeout=10/g" $PWD/rhcos_mount/grub2/grub.cfg

echo "DEBUG:"
echo "----- ostree-1-rhcos.conf -----"
cat $PWD/rhcos_mount/loader/entries/ostree-1-rhcos.conf
echo "----- ostree-1-rhcos.conf -----"


echo "### Step 10. RHCOS OS Image preparations - Unmount RHCOS OS Image raw file"
umount $PWD/rhcos_mount


echo "### Step 11. RHCOS OS Image preparations - Dettach RHCOS OS Image raw file from the loop device"
sleep 5
losetup --detach $LOOP


echo "### Last chance, irreversible actions starting in 10 seconds! ###"
echo "Press CTRL + C to cancel"
sleep 10

echo "### Step 12. RHCOS OS Image load to Bare Metal boot disk - Run disk/data duplicator binary (dd)"
sleep 5
dd if=$PWD/$RHCOS_IMAGE_NAME.raw of=/dev/sda bs=1M status=progress

echo "### Step 13. RHCOS OS Image load to Bare Metal boot disk - Verify"
echo "### Step 13 NOTICE - Ignore expected error GPT PMBR size mismatch"
# Inspect the written disk image via `fdisk -l` once the dd process is completed, which will show the difference.
# Commands `lsblk -f`, `parted -l` or `df -hT` will not reflect the change.
fdisk -l /dev/sda

echo "### Step 14. Hard Reboot"
echo "### Step 14 NOTICE - Open the IBM Cloud Console (Web GUI), select the Bare Metal, click Actions, then open both the 'VNC Console' and 'Serial Console'. This will show the RHCOS booting."
(sleep 5 && reboot -f &) && exit

```

#### Additional - Reboot host and configure GRUB Boot Options

- Enter GRUB Boot Options editor (to include the RHCOS igntion and network parameters). More instructions on editing GRUB Boot Options is shown within various Red Hat KB documents, for example [Red Hat KB - Performing an advanced RHEL 8 installation - Chapter 16. Boot options](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html/performing_an_advanced_rhel_8_installation/kickstart-and-advanced-boot-options_installing-rhel-as-an-experienced-user#proc_editing-the-grub2-menu_assembly_editing-boot-options).


## RH OCP configuration for new RHCOS Bare Metal host on the IBM Cloud VPC Infrastructure environment

Review and approve the pending certificate signing requests for the new RHCOS Bare Metal nodes

#### Commands for showing pending certificate signing requests

```shell
[root@bastion ~]# oc get csr
NAME        AGE   SIGNERNAME                                    REQUESTOR                                                                   REQUESTEDDURATION   CONDITION
csr-tx7sk   42s   kubernetes.io/kube-apiserver-client-kubelet   system:serviceaccount:openshift-machine-config-operator:node-bootstrapper   <none>              Pending

[root@bastion ~]# oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs oc adm certificate approve
certificatesigningrequest.certificates.k8s.io/csr-tx7sk approved

[root@bastion ~]# oc get csr
NAME        AGE     SIGNERNAME                                    REQUESTOR                                                                   REQUESTEDDURATION   CONDITION
csr-tx7sk   2m17s   kubernetes.io/kube-apiserver-client-kubelet   system:serviceaccount:openshift-machine-config-operator:node-bootstrapper   <none>              Approved,Issued
csr-xt27c   12s     kubernetes.io/kubelet-serving                 system:node:infra-3-bm                                                      <none>              Pending

[root@bastion ~]# oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs oc adm certificate approve
certificatesigningrequest.certificates.k8s.io/csr-xt27c approved
```

#### Commands for approving pending certificate signing requests

```shell
[root@bastion ~]# oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs oc adm certificate approve
```

#### Commands to show the new RHCOS Bare Metal noe

```shell
[root@bastion ~]# oc get no
NAME         STATUS   ROLES                  AGE     VERSION
control-1    Ready    master                 9d      v1.24.6+5658434
control-2    Ready    master                 9d      v1.24.6+5658434
control-3    Ready    master                 9d      v1.24.6+5658434
infra-1-bm   Ready    worker                 4d13h   v1.24.6+5658434
infra-2-bm   Ready    worker                 6d18h   v1.24.6+5658434
infra-3-bm   Ready    worker                 6m38s   v1.24.6+5658434
infra-4-bm   Ready    worker                 4d15h   v1.24.6+5658434
worker-1     Ready    infra,storage,worker   9d      v1.24.6+5658434
worker-2     Ready    infra,storage,worker   9d      v1.24.6+5658434
worker-3     Ready    infra,storage,worker   9d      v1.24.6+5658434
```


## RH CoreOS with Bare Metal on IBM Cloud VPC Infrastructure environment

| RHCOS Image | Success | Comments |
| --- | --- | --- |
| rhcos-4.11.9-x86_64-metal.x86_64.raw.gz | :white_check_mark: | This is dual BIOS/EEFI image with sector size as `512b`. Loads OS immediately. |
| rhcos-4.11.9-x86_64-metal4k.x86_64.raw.gz | :x: | `metal4k` version is UEFI only with sector size as `4k`. Does not work. Launches immediately to GRUB command line, configuration appears missing. |
| rhcos-4.12.2-x86_64-metal.x86_64.raw.gz | :x: | This is dual BIOS/EEFI image with sector size as `512b`. Corrupted boot with error `No filesystem could mount root, tried:` immediately followed by `Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)` |
| rhcos-4.12.2-x86_64-metal4k.x86_64.raw.gz | :x: | `metal4k` version is UEFI only with sector size as `4k`. Does not work. Launches immediately to GRUB command line, configuration appears missing. |
