# Insights Test Configuration
# Run comprehensive test suite for refactored codebase

import os
import sys
import unittest
from pathlib import Path

# Add the app path to Python path for imports
app_path = Path(__file__).parent.parent
if str(app_path) not in sys.path:
    sys.path.insert(0, str(app_path))

# Test configuration
TEST_CONFIG = {
    'verbose': True,
    'failfast': False,
    'catch_warnings': True,
    'test_modules': [
        'insights.tests.test_api_refactoring',
        'insights.tests.test_ml_functionality',
        'insights.tests.test_api_integration',
        'insights.tests.test_basic_workflow',
        'insights.tests.test_ai_insights_integration',
        'insights.tests.test_permissions'
    ],
    'coverage': {
        'enabled': True,
        'modules': [
            'insights.api.response',
            'insights.api.ml',
            'insights.api.ml.customer',
            'insights.api.ml.sales',
            'insights.api.ml.inventory',
            'insights.api.ml.financial',
            'insights.api.ml.procurement',
            'insights.api.ml.hr',
            'insights.api.ml.executive',
            'insights.api.ml.search',
            'insights.api.ml.general',
            'insights.ml.base',
            'insights.ml.customer_intelligence',
            'insights.ml.sales_intelligence',
            'insights.ml.inventory_intelligence',
            'insights.ml.financial_intelligence'
        ]
    }
}

def run_tests():
    """Run the complete test suite"""
    # Discover and run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for module_name in TEST_CONFIG['test_modules']:
        try:
            module = __import__(module_name, fromlist=[''])
            module_suite = loader.loadTestsFromModule(module)
            suite.addTest(module_suite)
            print(f"✓ Loaded tests from {module_name}")
        except ImportError as e:
            print(f"✗ Failed to load {module_name}: {e}")
        except Exception as e:
            print(f"✗ Error loading tests from {module_name}: {e}")

    # Run the tests
    runner = unittest.TextTestRunner(
        verbosity=2 if TEST_CONFIG['verbose'] else 1,
        failfast=TEST_CONFIG['failfast']
    )

    print(f"\n{'='*60}")
    print("RUNNING INSIGHTS REFACTORING TEST SUITE")
    print(f"{'='*60}")
    print(f"Test modules: {len(TEST_CONFIG['test_modules'])}")
    print(f"Coverage modules: {len(TEST_CONFIG['coverage']['modules'])}")
    print(f"{'='*60}\n")

    result = runner.run(suite)

    # Print summary
    print(f"\n{'='*60}")
    print("TEST RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.wasSuccessful():
        print("✓ ALL TESTS PASSED")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1

if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)