# Roku RCE

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

**Run**:
One start-to-stop period of a Cloud Device. It has its own address and is billed by the minute.
_Avoid_: session, instance, boot

**Snapshot**:
Saved Cloud Device state that a Run starts from.
_Avoid_: image, backup, checkpoint

**Dev Snapshot**:
The Snapshot marked as a Cloud Device's default, taken after developer mode and the Dev Password are set.
_Avoid_: base image, golden snapshot

**Dev Password**:
The password a Cloud Device's developer mode is protected with, needed to sideload and take screenshots. Set once during dev setup; each Cloud Device has its own.
_Avoid_: installer password, developer password

**Retired Cloud Device**:
A Cloud Device taken out of use. RCE cannot delete it, so it is renamed and dropped from the Device Names.
_Avoid_: deleted device, removed device
