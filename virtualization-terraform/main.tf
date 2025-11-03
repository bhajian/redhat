############################################################
# main.tf — KubeVirt VM + Terraform start/stop control
############################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">= 1.19.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.0"
    }
  }
}

# --- Providers ---
provider "kubectl" {
  config_path = "~/.kube/config"
}

# --- Power control (no manifest edits needed) ---
variable "vm_power_state" {
  description = "Desired power state of the VM: running or stopped"
  type        = string
  default     = "running"
  validation {
    condition     = contains(["running", "stopped"], lower(var.vm_power_state))
    error_message = "vm_power_state must be 'running' or 'stopped'."
  }
}

# --- Editable settings ---
locals {
  vm_name         = "rhel8-gray-cattle-98-tf"
  vm_namespace    = "default"

  # OS image DataSource (comes from OpenShift Virtualization OS images)
  datasource_ns   = "openshift-virtualization-os-images"
  datasource_name = "rhel8"

  disk_size_gi    = 30
  cpu_cores       = 1          # adjust as needed
  cpu_sockets     = 1
  cpu_threads     = 1
  memory_guest    = "2Gi"      # adjust as needed

  cloud_user      = "cloud-user"
  cloud_password  = "qmo4-6vks-ryv0"  # demo; rotate for real
}

# --- VirtualMachine (with inline DataVolumeTemplate) ---
resource "kubectl_manifest" "vm_rhel8" {
  yaml_body = <<-YAML
    apiVersion: kubevirt.io/v1
    kind: VirtualMachine
    metadata:
      name: ${local.vm_name}
      namespace: ${local.vm_namespace}
      labels:
        app: rhel8
    spec:
      # Default desired state on create; power control below can override.
      runStrategy: RerunOnFailure

      dataVolumeTemplates:
      - apiVersion: cdi.kubevirt.io/v1beta1
        kind: DataVolume
        metadata:
          name: ${local.vm_name}
        spec:
          sourceRef:
            kind: DataSource
            name: ${local.datasource_name}
            namespace: ${local.datasource_ns}
          storage:
            resources:
              requests:
                storage: ${local.disk_size_gi}Gi
            # To pin a storage class, add the line below WITHOUT interpolation:
            # storageClassName: ocs-external-storagecluster-ceph-rbd

      template:
        metadata:
          annotations:
            vm.kubevirt.io/flavor: small
            vm.kubevirt.io/os: rhel8
            vm.kubevirt.io/workload: server
          labels:
            kubevirt.io/domain: ${local.vm_name}
            kubevirt.io/size: small
        spec:
          architecture: amd64
          domain:
            cpu:
              cores: ${local.cpu_cores}
              sockets: ${local.cpu_sockets}
              threads: ${local.cpu_threads}
            memory:
              guest: ${local.memory_guest}
            machine:
              type: pc-q35-rhel9.4.0
            devices:
              rng: {}
              interfaces:
              - name: default
                model: virtio
                masquerade: {}
              disks:
              - name: rootdisk
                disk:
                  bus: virtio
              - name: cloudinitdisk
                disk:
                  bus: virtio
          networks:
          - name: default
            pod: {}
          volumes:
          - name: rootdisk
            dataVolume:
              name: ${local.vm_name}
          - name: cloudinitdisk
            cloudInitNoCloud:
              userData: |
                #cloud-config
                user: ${local.cloud_user}
                password: ${local.cloud_password}
                chpasswd: { expire: False }
          terminationGracePeriodSeconds: 180
  YAML
}

# --- Power control via oc patch (idempotent) ---
# Start (power on) when vm_power_state=running
resource "null_resource" "vm_power_on" {
  count      = lower(var.vm_power_state) == "running" ? 1 : 0
  depends_on = [kubectl_manifest.vm_rhel8]

  triggers = { state = lower(var.vm_power_state) }

  provisioner "local-exec" {
    command = "oc patch vm ${local.vm_name} -n ${local.vm_namespace} --type merge -p '{\"spec\":{\"runStrategy\":\"RerunOnFailure\"}}'"
  }
}

# Stop (power off) when vm_power_state=stopped
resource "null_resource" "vm_power_off" {
  count      = lower(var.vm_power_state) == "stopped" ? 1 : 0
  depends_on = [kubectl_manifest.vm_rhel8]

  triggers = { state = lower(var.vm_power_state) }

  provisioner "local-exec" {
    command = "oc patch vm ${local.vm_name} -n ${local.vm_namespace} --type merge -p '{\"spec\":{\"runStrategy\":\"Halted\"}}'"
  }
}

# --- Handy outputs ---
output "vm_name" {
  value = local.vm_name
}

output "vm_namespace" {
  value = local.vm_namespace
}
