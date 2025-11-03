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

## To stop and start a VM

Add a variable and update your resource:
```
variable "vm_runstrategy" {
  type    = string
  default = "RerunOnFailure" # change to "Halted" to stop
}

# then inside your manifest:
spec:
  runStrategy: ${var.vm_runstrategy}
```

Then run:
```
terraform apply -auto-approve
```

To stop:
```
terraform apply -var="vm_runstrategy=Halted" -auto-approve
```

To start:
```
terraform apply -var="vm_runstrategy=RerunOnFailure" -auto-approve
```

Terraform will patch the VM automatically.
