############################################################
# main.tf — Terraform drop-in to create a RHEL8 VM on OpenShift
# using the kubectl_manifest provider (no schema issues)
############################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">= 1.19.0"
    }
  }
}

# --- Provider ---
provider "kubectl" {
  config_path = "~/.kube/config"
}

# --- Local Variables ---
locals {
  vm_name         = "rhel8-gray-cattle-98-tf"
  vm_namespace    = "default"
  datasource_ns   = "openshift-virtualization-os-images"
  datasource_name = "rhel8"
  disk_size_gi    = 30
  cpu_cores       = 2
  cpu_sockets     = 1
  cpu_threads     = 1
  memory_guest    = "4Gi"
  cloud_user      = "cloud-user"
  cloud_password  = "qmo4-6vks-ryv0"
}

# --- VirtualMachine Resource ---
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
            # Uncomment this line to specify your storage class manually:
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

# --- Outputs ---
output "vm_name" {
  value = local.vm_name
}

output "vm_namespace" {
  value = local.vm_namespace
}
