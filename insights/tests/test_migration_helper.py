# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from migration_helper import InsightsAPIMigrator


class TestMigrationHelper(unittest.TestCase):
    """Test suite for the migration helper tool"""

    def setUp(self):
        """Set up test environment"""
        self.migrator = InsightsAPIMigrator()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_file(self, content, filename="test.py"):
        """Create a test file with given content"""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, 'w') as f:
            f.write(content)
        return file_path

    def test_scan_file_with_deprecated_imports(self):
        """Test scanning a file with deprecated imports"""
        content = '''
from insights.api.ml import customer_segmentation, sales_forecast
import insights.api.ml

def some_function():
    from insights.api.ml import inventory_classification
    pass
'''
        file_path = self.create_test_file(content)

        results = self.migrator.scan_file(file_path)

        self.assertIn('deprecated_imports', results)
        self.assertIn('functions_to_migrate', results)
        self.assertTrue(len(results['deprecated_imports']) > 0)
        self.assertIn('customer_segmentation', results['functions_to_migrate'])

    def test_scan_file_without_deprecated_imports(self):
        """Test scanning a file without deprecated imports"""
        content = '''
from insights.api.ml.customer import customer_segmentation
from insights.api.ml.sales import sales_forecast

def some_function():
    pass
'''
        file_path = self.create_test_file(content)

        results = self.migrator.scan_file(file_path)

        self.assertEqual(len(results['deprecated_imports']), 0)
        self.assertEqual(len(results['functions_to_migrate']), 0)

    def test_migrate_file_dry_run(self):
        """Test migrating a file in dry-run mode"""
        content = '''
from insights.api.ml import customer_segmentation
'''
        file_path = self.create_test_file(content)

        # Read original content
        with open(file_path, 'r') as f:
            original_content = f.read()

        # Migrate in dry-run mode
        success = self.migrator.migrate_file(file_path, dry_run=True)

        self.assertTrue(success)

        # Content should be unchanged in dry-run
        with open(file_path, 'r') as f:
            new_content = f.read()

        self.assertEqual(original_content, new_content)

    def test_migrate_file_actual(self):
        """Test migrating a file with actual changes"""
        content = '''
from insights.api.ml import customer_segmentation, sales_forecast
'''
        file_path = self.create_test_file(content)

        # Migrate with actual changes
        success = self.migrator.migrate_file(file_path, dry_run=False)

        self.assertTrue(success)

        # Check that file was modified
        with open(file_path, 'r') as f:
            new_content = f.read()

        self.assertIn('# DEPRECATED:', new_content)
        self.assertIn('MIGRATION REQUIRED:', new_content)

    def test_function_mapping_completeness(self):
        """Test that all major functions are mapped for migration"""
        # Check that key functions are in the mapping
        expected_functions = [
            'customer_segmentation',
            'sales_forecast',
            'inventory_classification',
            'financial_intelligence',
            'get_ml_status',
            'run_all_models'
        ]

        for func in expected_functions:
            self.assertIn(func, self.migrator.FUNCTION_MAPPING,
                         f"Function {func} not found in migration mapping")

    def test_scan_project_functionality(self):
        """Test scanning an entire project directory"""
        # Create multiple test files
        self.create_test_file('from insights.api.ml import customer_segmentation', 'file1.py')
        self.create_test_file('from insights.api.ml import sales_forecast', 'file2.py')
        self.create_test_file('print("no imports")', 'file3.py')

        results = self.migrator.scan_project(self.temp_dir)

        self.assertIn('summary', results)
        self.assertIn('files_with_deprecated_imports', results)
        self.assertEqual(results['summary']['total_files_scanned'], 3)
        self.assertEqual(results['summary']['files_with_deprecated_imports'], 2)

    def test_migration_preserves_functionality(self):
        """Test that migration doesn't break basic Python syntax"""
        content = '''
def existing_function():
    return "test"

from insights.api.ml import customer_segmentation

class ExistingClass:
    def method(self):
        from insights.api.ml import sales_forecast
        return sales_forecast()
'''
        file_path = self.create_test_file(content)

        # Should migrate without breaking syntax
        success = self.migrator.migrate_file(file_path, dry_run=False)

        self.assertTrue(success)

        # File should still be valid Python
        with open(file_path, 'r') as f:
            migrated_content = f.read()

        # Should be able to compile (basic syntax check)
        try:
            compile(migrated_content, file_path, 'exec')
        except SyntaxError:
            self.fail("Migration broke Python syntax")

    def test_migration_comments_are_helpful(self):
        """Test that migration adds helpful comments"""
        content = 'from insights.api.ml import customer_segmentation'
        file_path = self.create_test_file(content)

        self.migrator.migrate_file(file_path, dry_run=False)

        with open(file_path, 'r') as f:
            content = f.read()

        self.assertIn('MIGRATION REQUIRED', content)
        self.assertIn('DEPRECATION_NOTICE.md', content)
        self.assertIn('insights.api.ml.customer', content)


class TestMigrationMapping(unittest.TestCase):
    """Test the migration function mapping"""

    def setUp(self):
        self.migrator = InsightsAPIMigrator()

    def test_all_mappings_point_to_valid_modules(self):
        """Test that all migration mappings point to existing modules"""
        valid_modules = [
            'insights.api.ml.customer',
            'insights.api.ml.sales',
            'insights.api.ml.inventory',
            'insights.api.ml.procurement',
            'insights.api.ml.financial',
            'insights.api.ml.hr',
            'insights.api.ml.executive',
            'insights.api.ml.search',
            'insights.api.ml.general'
        ]

        for func, target_module in self.migrator.FUNCTION_MAPPING.items():
            self.assertIn(target_module, valid_modules,
                         f"Function {func} maps to invalid module {target_module}")

    def test_no_duplicate_mappings(self):
        """Test that no function is mapped to multiple modules"""
        mappings = self.migrator.FUNCTION_MAPPING
        targets = list(mappings.values())
        unique_targets = set(targets)

        self.assertEqual(len(targets), len(unique_targets),
                        "Found duplicate mappings in migration table")

    def test_mapping_keys_are_valid_function_names(self):
        """Test that mapping keys look like valid Python function names"""
        import re

        for func_name in self.migrator.FUNCTION_MAPPING.keys():
            # Should be valid Python identifier
            self.assertTrue(func_name.isidentifier(),
                          f"Invalid function name: {func_name}")

            # Should not contain spaces or special chars (except underscore)
            self.assertRegex(func_name, r'^[a-zA-Z_][a-zA-Z0-9_]*$',
                           f"Function name contains invalid characters: {func_name}")


if __name__ == '__main__':
    unittest.main()