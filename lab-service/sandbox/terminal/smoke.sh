set -eu
test "$(id -u)" = 1000
if git -C /workspace/project rev-parse --is-inside-work-tree >/dev/null 2>&1; then exit 1; fi
git init /workspace/project >/dev/null 2>&1
git -C /workspace/project config user.name Student
git -C /workspace/project config user.email student@example.test
printf 'My first repository\n' > /workspace/project/README.md
git -C /workspace/project add README.md
git -C /workspace/project commit -m 'Initial commit' >/dev/null
git -C /workspace/project switch -c feature/lab >/dev/null 2>&1
test "$(git -C /workspace/project rev-parse --is-inside-work-tree)" = true
p=$(readlink -f -- /workspace/project/README.md)
case "$p" in /workspace/*) true;; *) exit 1;; esac
grep -Fq -- 'My first repository' "$p"
test "$(git -C /workspace/project log -1 --format=%s)" = 'Initial commit'
git -C /workspace/project show HEAD:README.md | grep -Fq 'My first repository'
test "$(git -C /workspace/project branch --show-current)" = feature/lab
git -C /workspace/project switch -c wrong-branch >/dev/null 2>&1
if test "$(git -C /workspace/project branch --show-current)" = feature/lab; then exit 1; fi
printf 'Git lab: non-root restricted runtime, all four verifiers and negative branch check passed\n'
