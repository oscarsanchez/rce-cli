# rce-cli

A command-line tool and agent skill for using Roku Cloud Emulator from any Roku project.

## Language

**RCE**:
Roku Cloud Emulator, Roku's paid service that hosts Cloud Devices.
_Avoid_: the emulator, the cloud

**Cloud Device**:
A virtual Roku player or TV hosted by RCE. It is permanent once created and counts against the org quota for good.
_Avoid_: emulator, RCE instance, simulator, virtual device

**Device Name**:
The local name a user gives a Cloud Device, mapped to its RCE id.
_Avoid_: alias, nickname, label

**Per-user config**:
The file on a person's machine, shared by every project, that holds their Device Names and what rce stores with each.
_Avoid_: device config, devices file, settings file

**Run**:
One start-to-stop period of a Cloud Device. It has its own address and is billed by the minute.
_Avoid_: session, instance, boot

**Firmware**:
The Roku OS build a Run runs, chosen when the Run starts. RCE offers two per device type: the current public release and the next release still in development.
_Avoid_: OS version, Roku OS version

**Snapshot**:
Saved Cloud Device state that a Run starts from.
_Avoid_: image, backup, checkpoint

**Base Snapshot**:
The factory-state Snapshot RCE gives every Cloud Device when it is created.
_Avoid_: initial snapshot, factory snapshot

**Live Snapshot**:
The Snapshot RCE saves of a Cloud Device's state at every stop.
_Avoid_: last state, latest snapshot

**Dev Snapshot**:
The Snapshot marked as a Cloud Device's default, taken after developer mode and the Dev Password are set.
_Avoid_: base image, golden snapshot

**Dev Password**:
The password a Cloud Device's developer mode is protected with, needed to sideload and take screenshots. Set once during dev setup; each Cloud Device has its own.
_Avoid_: installer password, developer password

**Pool**:
A set of interchangeable dev-ready Cloud Devices from which a pipeline takes whichever one is free.
_Avoid_: fleet, farm, device group

**Pool member**:
A Cloud Device listed in a Pool. It is a Free Cloud Device whenever it has no Run.
_Avoid_: slot, worker

**Free Cloud Device**:
A Cloud Device with no Run, pending or running.
_Avoid_: idle device, open device, available device

**Claim**:
Starting a Run on any Free Cloud Device of a Pool. The Run is the claim; stopping it frees the Cloud Device.
_Avoid_: lease, reserve, allocate

**Retired Cloud Device**:
A Cloud Device taken out of use. RCE cannot delete it, so it is renamed and dropped from the Device Names.
_Avoid_: deleted device, removed device
