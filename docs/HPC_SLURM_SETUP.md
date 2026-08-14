# Trusted Slurm integration for virtual labs

The application server is not the HPC cluster. A learner never receives a
cluster password, private key, `ssh` prompt, arbitrary SSH host, or a raw
remote command. They submit a batch script through the lab page; the service
submits it to one operator-approved Slurm profile and records the returned job
ID as `PENDING`.

## Responsibilities

| Role | What they configure |
| --- | --- |
| HPC operator / platform administrator | The trusted SSH endpoint, a submit-only account, an Ed25519 key, pinned host keys, Slurm account/QoS policy and the deployment environment. |
| Lab administrator (teacher) | A selected `hpc_profile_id`, partition/account/QoS already allowlisted by the profile, and per-lab limits that only narrow the profile limits. |
| Learner | An `sbatch` script and a resource request within the lab limits. They can view their own job ID/status, but do not open an SSH terminal. |

Only an `ADMIN` can edit labs in this deployment. If teachers need this role,
assign it through the identity-management flow rather than bypassing the API.

## Required HPC-side controls

Create a dedicated Slurm service account for this integration. It must be
limited by Slurm `Account`/`QOS` and partition ACLs: maximum TRES, wall time,
job count, submit rate and storage quota. Do **not** give it sudo, shared home
directories with administrators, login-shell access from learners, or access
to the application database.

The service strips learner `#SBATCH` lines and supplies partition, account,
QoS and resource flags itself. This is defense in depth only: the Slurm QOS
must still prevent a script from submitting child jobs or consuming resources
beyond the profile policy.

## Kubernetes secret

On the application cluster, create this secret from a secure operator machine.
The private key and `known_hosts` are never committed, pasted into the UI or
stored in `runtime_config`.

```bash
kubectl -n default create secret generic hpc-slurm-credentials \
  --from-file=id_ed25519=/secure/path/lab-submit-ed25519 \
  --from-file=known_hosts=/secure/path/hpc-known_hosts
```

`known_hosts` must contain the login node's pinned host key. Do not use
`StrictHostKeyChecking=no`, `sshpass`, a password, or `UserKnownHostsFile=/dev/null`.

## Deployment profile

Set these non-secret deployment variables through the protected production
configuration. Use the real values for the target HPC cluster; the example is
only a shape, not a command to run unchanged.

```text
SLURM_ENABLED=true
SLURM_PROFILE_ID=hpcc-teaching-2026
SLURM_PROFILE_LABEL=HPC teaching queue
SLURM_TRANSPORT=SSH
SLURM_SSH_HOST=login.hpc.example.edu
SLURM_SSH_PORT=22
SLURM_SSH_USER=bdc_lab_submit
SLURM_SSH_IDENTITY_FILE=/etc/lab-hpc/id_ed25519
SLURM_SSH_KNOWN_HOSTS_FILE=/etc/lab-hpc/known_hosts
SLURM_COMMAND_TIMEOUT=20s
SLURM_DEFAULT_PARTITION=teaching
SLURM_DEFAULT_ACCOUNT=students
SLURM_DEFAULT_QOS=teaching
SLURM_ALLOWED_PARTITIONS=teaching
SLURM_ALLOWED_ACCOUNTS=students
SLURM_ALLOWED_QOS=teaching
SLURM_MAX_NODES=1
SLURM_MAX_TASKS=32
SLURM_MAX_CPUS_PER_TASK=16
SLURM_MAX_MEMORY_MB=65536
SLURM_MAX_GPU_COUNT=0
SLURM_MAX_TIME=01:00:00
```

The deployment copies the mounted key to an in-memory volume owned by the
non-root service user with mode `0400`; OpenSSH will reject a private key with
weaker permissions. The application fails closed when the profile, credential
files, host key or allowlists are absent. It does not return a fake completed
result.

## Create a lab

In **Lab Management → Sandbox & Runtime**, choose the installed profile ID and
enter the approved partition, account and QoS. Set limits that are at or below
the profile limits. For example: one node, four tasks, two CPUs/task, 4096 MB,
no GPU and 15 minutes. The learner page then exposes a batch-script editor and
a **Submit to Slurm** button, not a terminal.

## Before enabling learners

1. Submit a harmless `hostname` job with the service account and verify its
   Slurm ID appears in the lab as `PENDING`.
2. Verify a request above each lab limit is rejected before SSH is invoked.
3. Verify the Slurm QOS rejects a nested `sbatch` and over-limit allocation.
4. Check that the credentials mount is read-only, host-key pinning is active,
   and the service pod is non-root with a read-only filesystem.
5. Configure Slurm accounting/log retention and a job-status collector before
   using job completion as a grading signal. This change only records
   submission acceptance; it does not infer scientific or grading success.
