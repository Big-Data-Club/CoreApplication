import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('legacy_selection',Path(__file__).resolve().parents[1]/'select-legacy-workloads.py')
selection=importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)

class SelectionTests(unittest.TestCase):
    def test_warehouse_docs_and_infrastructure_do_not_restart_apps(self):
        paths=['data-warehouse','k3s/data-warehouse/resources.json','.github/workflows/data-warehouse-production.yml','docs/DATA_PLATFORM.md']
        self.assertEqual(selection.select(paths),[])

    def test_application_sources_select_only_their_deployments(self):
        self.assertEqual(selection.select(['lms-service/a.go','lms-service/b.go','chat-service/a.go']),['lms-service','chat-service'])

    def test_submodule_pointer_is_a_real_source_change(self):
        self.assertEqual(selection.select(['dutylog']),['dutylog-service'])
