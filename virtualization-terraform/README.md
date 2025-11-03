# GitOps with Terraform & OpenShift Virtualization

The following terraform provider is capable of the following tasks and more:
- Creating a VM
- Updating the number of cores and memory for that VM
- Add a GPU to a VM
- Turn on/off a VM
- etc

## To create a VM
1- Download the main.tf
2- run 
```
terraform init
terraform apply -auto-approve
```
## To change number of cores change the following lines in main.tf:
```
  cpu_cores    = 2        # was 1
  memory_guest = "4Gi"    # was "2Gi"
```
Then
```
terraform apply -auto-approve
```

## To stop and start a VM

To stop:
```
terraform apply -auto-approve -var="vm_power_state=stopped"
```

To start:
```
terraform apply -auto-approve -var="vm_power_state=running" 
```

Terraform will patch the VM automatically.

## To Delete
```
terraform destroy
```
