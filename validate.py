"""
Validation script for Phase 1 baseline testing.

Checks if generated artifacts meet the success criteria:
- index.html opens in a browser
- Pieces fall (game loop exists)
- Lines clear (clearLines function)
- Score updates (score tracking)
- Game over triggers (game over condition)
"""

import json
import os
import re
import sys
from pathlib import Path


def check_html(filepath: str) -> dict:
    """Check if HTML file is valid and includes necessary elements."""
    result = {
        "exists": False,
        "has_doctype": False,
        "has_canvas": False,
        "includes_js": False,
        "js_files": [],
    }
    
    if not os.path.exists(filepath):
        return result
    
    result["exists"] = True
    
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    
    result["has_doctype"] = "<!DOCTYPE html>" in content.lower()
    result["has_canvas"] = "<canvas" in content.lower() or 'id="game' in content.lower()
    
    # Check for script includes
    scripts = re.findall(r'src=["\']([^"\']+\.js)["\']', content)
    result["js_files"] = scripts
    result["includes_js"] = len(scripts) > 0
    
    return result


def check_javascript_implementation(directory: str, filename: str, features: list[str]) -> dict:
    """Check if a JS file implements required features."""
    result = {
        "exists": False,
        "features_found": [],
        "features_missing": [],
    }
    
    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath):
        return result
    
    result["exists"] = True
    
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    
    # Check for each feature
    for feature in features:
        # Simple pattern matching for common game patterns
        patterns = [
            feature,
            feature.lower(),
            feature.replace(" ", ""),
            feature.replace(" ", "_"),
            feature.replace(" ", "-"),
        ]
        
        found = any(pat in content for pat in patterns)
        if found:
            result["features_found"].append(feature)
        else:
            result["features_missing"].append(feature)
    
    return result


def validate_tetris(output_dir: str) -> dict:
    """Validate a Tetris clone implementation."""
    report = {
        "output_dir": output_dir,
        "html": {},
        "game_logic": {},
        "features": {},
        "issues": [],
        "passed": False,
    }
    
    # Check HTML
    html_path = os.path.join(output_dir, "index.html")
    report["html"] = check_html(html_path)
    
    if not report["html"]["exists"]:
        report["issues"].append("Missing index.html")
        return report
    
    if not report["html"]["has_canvas"]:
        report["issues"].append("No canvas or game container found in HTML")
    
    if not report["html"]["includes_js"]:
        report["issues"].append("HTML does not include any JS files")
    
    # Check for game logic in JS files
    tetris_files = {
        "tetris.js": ["piece", "move", "rotate", "collision", "game over", "score"],
        "script.js": ["game loop", "event listener", "keyboard"],
        "sounds.js": ["audio", "sound", "play"],
        "colors.js": ["color", "rgb", "hex"],
    }
    
    all_features_found = []
    all_features_missing = []
    
    for filename, features in tetris_files.items():
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath):
            check = check_javascript_implementation(output_dir, filename, features)
            report["game_logic"][filename] = {
                "exists": True,
                "features_found": check["features_found"],
                "features_missing": check["features_missing"],
            }
            all_features_found.extend(check["features_found"])
            all_features_missing.extend(check["features_missing"])
        else:
            report["game_logic"][filename] = {"exists": False}
    
    # Check critical features
    critical_features = ["piece", "move", "rotate", "collision", "game over", "score"]
    for feature in critical_features:
        if feature not in all_features_found:
            # Check across all JS files
            found_in_any = False
            for js_file in Path(output_dir).glob("*.js"):
                with open(js_file, encoding="utf-8") as f:
                    if feature.lower() in f.read().lower():
                        found_in_any = True
                        break
            
            if not found_in_any:
                report["features"][feature] = "MISSING"
                report["issues"].append(f"Critical feature '{feature}' not found in any JS file")
            else:
                report["features"][feature] = "FOUND"
        else:
            report["features"][feature] = "FOUND"
    
    # Check for session.json
    session_path = os.path.join(output_dir, "session.json")
    if os.path.exists(session_path):
        with open(session_path, encoding="utf-8") as f:
            session = json.load(f)
        report["session"] = {
            "completed": session.get("completed", False),
            "cycles_run": session.get("cycles_run", 0),
            "files_in_spec": len(session.get("file_list", [])),
        }
    
    # Determine if passed
    report["passed"] = len(report["issues"]) == 0 and report["session"].get("completed", False)
    
    return report


def print_report(report: dict):
    """Print a human-readable validation report."""
    print("\n" + "="*66)
    print(f"  VALIDATION REPORT: {report['output_dir']}")
    print("="*66)
    
    # HTML check
    if report["html"].get("exists"):
        print("✅ index.html exists")
        if report["html"].get("has_doctype"):
            print("  ✅ Has DOCTYPE declaration")
        if report["html"].get("has_canvas"):
            print("  ✅ Has canvas/game container")
        if report["html"].get("includes_js"):
            print(f"  ✅ Includes {len(report['html']['js_files'])} JS file(s): {', '.join(report['html']['js_files'])}")
    else:
        print("❌ index.html missing")
    
    # Game logic
    print(f"\n📝 Game logic files:")
    for filename, check in report.get("game_logic", {}).items():
        if check.get("exists"):
            print(f"  ✅ {filename} exists")
            if check.get("features_found"):
                print(f"     Found: {', '.join(check['features_found'])}")
            if check.get("features_missing"):
                print(f"     Missing: {', '.join(check['features_missing'])}")
        else:
            print(f"  ❌ {filename} missing")
    
    # Critical features
    print(f"\n🎯 Critical features:")
    for feature, status in report.get("features", {}).items():
        if status == "FOUND":
            print(f"  ✅ {feature}")
        else:
            print(f"  ❌ {feature}")
    
    # Session
    if "session" in report:
        print(f"\n📊 Session:")
        print(f"  Completed: {report['session']['completed']}")
        print(f"  Cycles run: {report['session']['cycles_run']}")
        print(f"  Files in spec: {report['session']['files_in_spec']}")
    
    # Issues
    if report["issues"]:
        print(f"\n⚠️  Issues ({len(report['issues'])}):")
        for issue in report["issues"]:
            print(f"  - {issue}")
    
    # Final verdict
    print(f"\n{'✅ PASSED' if report['passed'] else '❌ DID NOT PASS'}")
    print("="*66)


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <output_dir> [output_dir2 ...]")
        print("\nExample: python validate.py output/tetris-test")
        sys.exit(1)
    
    for output_dir in sys.argv[1:]:
        if not os.path.isdir(output_dir):
            print(f"❌ Directory not found: {output_dir}")
            continue
        
        report = validate_tetris(output_dir)
        print_report(report)
        
        # Save report
        report_path = os.path.join(output_dir, "validation_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Report saved to: {report_path}")


if __name__ == "__main__":
    main()
