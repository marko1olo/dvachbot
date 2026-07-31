import os
import subprocess
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def run_git(args, cwd="."):
    result = subprocess.run(
        ["git"] + args, 
        capture_output=True, 
        encoding="utf-8", 
        errors="replace", 
        cwd=cwd
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git command failed: git {' '.join(args)}\nError: {result.stderr}")
    return result.stdout.strip()

def get_unmerged_branches():
    run_git(["fetch", "origin"])
    output = run_git(["branch", "-r", "--no-merged", "origin/main"])
    branches = []
    for line in output.split('\n'):
        line = line.strip()
        if line and not line.startswith('*') and "origin/HEAD" not in line:
            branches.append(line)
    return branches

def _check_noise(files, diff_text):
    noise_extensions = {'.log', '.txt', '.png', '.json'}
    all_noise = True
    for f in files:
        path = Path(f)
        if path.suffix not in noise_extensions and path.name not in ["plan.md", "AUTONOMOUS_PROGRESS.md", "readme.md"]:
            all_noise = False
            break
            
    if not diff_text.strip() or (files and all_noise):
        return "REJECT", "Noise: Only non-code/report files modified or empty diff."
    return None

def _check_reject_criteria(added_lines, deleted_lines, short_name):
    for line in added_lines:
        if "execute" in line:
            if "f\"" in line or "f'" in line:
                if "{" in line and "}" in line and not any(k in line for k in ["?", "placeholder"]):
                    return "REJECT", "Security: Possible SQL Injection using f-strings in database execution."
            if "%" in line and any(sql in line.lower() for sql in ["select", "insert", "update", "delete", "where"]):
                return "REJECT", "Security: Possible SQL Injection using % operator in SQL query."
            if ".format(" in line and any(sql in line.lower() for sql in ["select", "insert", "update", "delete", "where"]):
                return "REJECT", "Security: Possible SQL Injection using .format() in SQL query."

    for line in added_lines:
        if "subprocess" in line or "os.system" in line or "Popen" in line:
            if "shell=True" in line:
                return "REJECT", "Security: Dangerous use of shell=True in subprocess call."
                
    for line in added_lines:
        if any(token_var in line.lower() for token_var in ["token =", "api_key =", "secret =", "password ="]):
            if '"' in line or "'" in line:
                if not any(t in short_name for t in ["test", "improve-status-check"]):
                    return "REJECT", "Security: Hardcoded API token / key detected."

    deleted_test_funcs = 0
    added_test_funcs = 0
    for line in deleted_lines:
        if "def test_" in line:
            deleted_test_funcs += 1
    for line in added_lines:
        if "def test_" in line:
            added_test_funcs += 1
    if deleted_test_funcs > 0 and added_test_funcs < deleted_test_funcs:
        return "REJECT", "Antipattern: Deleting existing test cases without adequate replacements."

    return None

def _check_manual_review(files, total_changes):
    if total_changes > 150:
        return "MANUAL_REVIEW", f"Lines count too high ({total_changes} lines changed)."
        
    for f in files:
        if "db_pool.py" in f or "database.py" in f or "bot_pool.py" in f:
            return "MANUAL_REVIEW", f"Core database/pool logic modified: {f}"

    return None

def _check_accept_criteria(files, added_lines, deleted_lines, total_changes, short_name):
    is_test_branch = any(t in short_name for t in ["test-", "testing-", "tests-", "improve-status-check"])
    all_test_files = all("test" in f or f.startswith("tests/") for f in files)
    if is_test_branch or all_test_files:
        return "ACCEPT", "Testing: Addition or improvement of unit tests."
        
    any(c in short_name for c in ["remove-unused", "cleanup", "chore", "clean"])
    only_imports_or_comments = True
    for line in added_lines:
        stripped = line.strip()
        if stripped and not (stripped.startswith("import ") or stripped.startswith("from ") or stripped.startswith("#") or stripped == ""):
            only_imports_or_comments = False
            break
    if only_imports_or_comments and len(deleted_lines) > 0:
        return "ACCEPT", "Cleanup: Removing unused imports, commented code, or dead logic."
        
    is_fix_branch = any(f in short_name for f in ["fix-", "security-fix-", "improve-"])
    if is_fix_branch:
        safety_patterns = ["is None", "is not None", "len(", "try:", "except", "sanitize", "clean"]
        has_safety = any(any(p in line for p in safety_patterns) for line in added_lines)
        if has_safety and total_changes < 50:
            return "ACCEPT", "Safety: Small safety checks, boundary/null validations or sanitizations."

    if all(f.endswith('.md') or f.endswith('.txt') for f in files):
        return "ACCEPT", "Documentation: Modifying markdown/text docs."

    if total_changes < 50:
        if "optimize" in short_name or "perf" in short_name:
            return "ACCEPT", "Performance: Minor performance optimizations."
        return "ACCEPT", "Acceptable minor improvements or refactoring."

    return None

def classify_branch(branch, cwd="."):
    short_name = branch.replace("origin/", "")

    try:
        files_output = run_git(["diff", "--name-only", "origin/main..." + branch], cwd=cwd)
        files = [f.strip() for f in files_output.split('\n') if f.strip()]
    except Exception as e:
        return "MANUAL_REVIEW", f"Failed to get diff files: {e}", [], 0, 0

    try:
        diff_text = run_git(["diff", "origin/main..." + branch], cwd=cwd)
    except Exception as e:
        return "MANUAL_REVIEW", f"Failed to get diff text: {e}", files, 0, 0

    added_lines = []
    deleted_lines = []
    for line in diff_text.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            added_lines.append(line[1:])
        elif line.startswith('-') and not line.startswith('---'):
            deleted_lines.append(line[1:])

    add_count = len(added_lines)
    del_count = len(deleted_lines)
    total_changes = add_count + del_count

    noise_decision = _check_noise(files, diff_text)
    if noise_decision:
        return noise_decision[0], noise_decision[1], files, add_count, del_count

    reject_decision = _check_reject_criteria(added_lines, deleted_lines, short_name)
    if reject_decision:
        return reject_decision[0], reject_decision[1], files, add_count, del_count

    manual_review_decision = _check_manual_review(files, total_changes)
    if manual_review_decision:
        return manual_review_decision[0], manual_review_decision[1], files, add_count, del_count

    accept_decision = _check_accept_criteria(files, added_lines, deleted_lines, total_changes, short_name)
    if accept_decision:
        return accept_decision[0], accept_decision[1], files, add_count, del_count

    return "MANUAL_REVIEW", "Does not clearly match auto-accept/auto-reject criteria.", files, add_count, del_count

def run_tests(cwd="."):
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], 
        capture_output=True, 
        encoding="utf-8", 
        errors="replace", 
        cwd=cwd
    )
    return result.returncode == 0, result.stdout + "\n" + result.stderr

def count_test_issues(test_output):
    summary_match = re.search(r'FAILED \((.*?)\)', test_output)
    if not summary_match:
        lines = test_output.split('\n')
        for line in reversed(lines):
            if line.strip():
                if "OK" in line:
                    return 0
                break
        if "FAILED" in test_output:
            return max(1, test_output.count("======================================================================"))
        return 0
    
    details = summary_match.group(1)
    issues = 0
    for part in details.split(','):
        part = part.strip()
        if 'failures' in part or 'errors' in part:
            try:
                issues += int(part.split('=')[1])
            except ValueError:
                pass
    return issues

def verify_syntax_locally(files, cwd="."):
    for f in files:
        if f.endswith('.py'):
            full_path = os.path.join(cwd, f)
            if not os.path.exists(full_path):
                continue
            res = subprocess.run(
                [sys.executable, "-m", "py_compile", f],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd
            )
            if res.returncode != 0:
                return False, f"Syntax check failed for {f}:\n{res.stderr}"
    return True, ""

def audit_branches(branches, cwd):
    report = []
    accept_branches = []
    reject_branches = []
    manual_review_branches = []
    
    print("\n=== Step 2: Auditing branches ===")
    for branch in branches:
        decision, reason, files, add_count, del_count = classify_branch(branch, cwd=cwd)
        record = {
            "branch": branch,
            "decision": decision,
            "reason": reason,
            "files": files,
            "additions": add_count,
            "deletions": del_count
        }
        report.append(record)
        
        if decision == "ACCEPT":
            accept_branches.append((branch, files))
        elif decision == "REJECT":
            reject_branches.append(branch)
        else:
            manual_review_branches.append(branch)
            
    # Save JSON report
    report_file = os.path.join(cwd, "audit_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nAudit report saved to {report_file}")
    
    print("\nClassification Summary:")
    print(f"ACCEPT: {len(accept_branches)}")
    print(f"REJECT: {len(reject_branches)}")
    print(f"MANUAL_REVIEW: {len(manual_review_branches)}")
    
    return report, accept_branches, reject_branches, manual_review_branches


def auto_merge_branches(accept_branches, cwd):
    print("\n=== Step 3: Auto-merging ACCEPT branches ===")
    merged_successfully = []
    conflicts = []
    syntax_failures = []
    
    for branch, files in accept_branches:
        print(f"Attempting to merge {branch}...")
        try:
            # Run git merge
            subprocess.run(
                ["git", "merge", "--no-ff", "-m", f"Merge remote-tracking branch '{branch}'", branch], 
                cwd=cwd,
                check=True, 
                capture_output=True,
                encoding="utf-8",
                errors="replace"
            )
            
            # Fast syntax check
            syntax_ok, syntax_err = verify_syntax_locally(files, cwd=cwd)
            if syntax_ok:
                print(f"  Merged cleanly: {branch}")
                merged_successfully.append(branch)
            else:
                print(f"  ERR: Syntax verification failed on {branch}. Reverting merge.")
                subprocess.run(
                    ["git", "reset", "--hard", "HEAD~1"], 
                    cwd=cwd,
                    check=True, 
                    capture_output=True
                )
                syntax_failures.append({"branch": branch, "error": syntax_err})
                
        except subprocess.CalledProcessError:
            print(f"  ERR: Conflict or merge failure on {branch}. Aborting merge.")
            subprocess.run(["git", "merge", "--abort"], cwd=cwd, capture_output=True)
            status_out = run_git(["status", "--porcelain"], cwd=cwd)
            conflicts.append({"branch": branch, "status": status_out})
            
    print(f"\nMerged clean candidates: {len(merged_successfully)}")
    return merged_successfully, conflicts, syntax_failures


def verify_and_rollback(merged_successfully, baseline_issues, cwd):
    # Final Verification and self-healing rollback
    print("\n=== Step 4: Final verification and self-healing ===")
    test_ok, test_output = run_tests(cwd=cwd)
    final_issues = count_test_issues(test_output)
    print(f"Final test issues: {final_issues} (baseline: {baseline_issues})")
    
    test_failures = []
    if final_issues > baseline_issues:
        print("ERR: Merged batch introduced new test failures! Commencing self-healing rollback...")
        for branch in reversed(merged_successfully.copy()):
            print(f"Reverting merge of {branch}...")
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=cwd, check=True, capture_output=True)
            merged_successfully.remove(branch)
            test_failures.append(branch)
            
            # Test again to see if we restored green status
            test_ok, test_output = run_tests(cwd=cwd)
            current_issues = count_test_issues(test_output)
            print(f"Issues after reverting {branch}: {current_issues}")
            if current_issues <= baseline_issues:
                print("OK: Restored green state.")
                break
                
    return merged_successfully, test_failures


def save_merge_summary(merged_successfully, conflicts, syntax_failures, test_failures, manual_review_branches, report, cwd):
    print("\n=== Auto-merge Summary ===")
    print(f"Merged successfully: {len(merged_successfully)}")
    print(f"Conflicts: {len(conflicts)}")
    print(f"Syntax failures: {len(syntax_failures)}")
    print(f"Rolled back due to test failures: {len(test_failures)}")
    
    # Save merge summary
    merge_summary = {
        "merged_successfully": merged_successfully,
        "conflicts": conflicts,
        "syntax_failures": syntax_failures,
        "test_failures": test_failures,
        "manual_review": manual_review_branches,
        "rejected": [r for r in report if r["decision"] == "REJECT"]
    }
    summary_file = os.path.join(cwd, "merge_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(merge_summary, f, indent=2, ensure_ascii=False)
    print(f"Merge summary saved to {summary_file}")


def main():
    repo_path = "C:\\Users\\danat\\Desktop\\dvachbot"
    print("=== Step 1: Gathering unmerged branches ===")
    try:
        branches = get_unmerged_branches()
    except Exception as e:
        print(f"Error fetching branches: {e}")
        sys.exit(1)

    print(f"Found {len(branches)} unmerged branches.")

    # Gather test baseline
    print("\n=== Gathering test baseline ===")
    baseline_ok, baseline_output = run_tests(cwd=repo_path)
    baseline_issues = count_test_issues(baseline_output)
    print(f"Baseline tests OK: {baseline_ok}. Total baseline issues/failures: {baseline_issues}")

    report, accept_branches, reject_branches, manual_review_branches = audit_branches(branches, repo_path)

    merged_successfully, conflicts, syntax_failures = auto_merge_branches(accept_branches, repo_path)

    merged_successfully, test_failures = verify_and_rollback(merged_successfully, baseline_issues, repo_path)

    save_merge_summary(merged_successfully, conflicts, syntax_failures, test_failures, manual_review_branches, report, repo_path)


if __name__ == "__main__":
    main()
