"""
Run all tests at once
Run: python test_all.py
"""
import subprocess
import sys

def run_test(test_name, script_name):
    print("\n" + "="*60)
    print(f"▶️  RUNNING: {test_name}")
    print("="*60)
    
    result = subprocess.run(
        [sys.executable, script_name],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ {test_name} PASSED")
        if result.stdout:
            # Print only the last few lines for brevity
            lines = result.stdout.split('\n')
            for line in lines[-5:]:
                print(f"   {line}")
    else:
        print(f"❌ {test_name} FAILED")
        if result.stderr:
            print(f"   Error: {result.stderr[:200]}")
    
    return result.returncode

if __name__ == "__main__":
    print("🚀 RUNNING ALL TESTS")
    print("Make sure you've set your API keys in each test file!")
    
    # Run tests
    tests = [
        ("Single Image", "test_single_image.py"),
        ("Carousel", "test_carousel.py"),
        ("Reel", "test_reel.py"),
    ]
    
    results = []
    for name, script in tests:
        if not os.path.exists(script):
            print(f"⚠️  Test file not found: {script}")
            continue
        result = run_test(name, script)
        results.append((name, result))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    for name, result in results:
        status = "✅ PASSED" if result == 0 else "❌ FAILED"
        print(f"  {name}: {status}")
    print("="*60)