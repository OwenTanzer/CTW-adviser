import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'scripts/verify_sources.py'
spec=importlib.util.spec_from_file_location('verify_sources',MODULE)
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class SourceContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.path=self.root/'sample.csv'
        self.data=b'key,culture,value,flag\na,*,0,true\nb,restricted,-1,false\nc,*, ,true\n'.replace(b', ,',b',,')
        self.path.write_bytes(self.data)
        self.schema={'path':'sample.csv','role':'lookup','keys':['key','culture'],'expected_rows':3,
          'columns':[{'name':n,'type':t,'nullable':n=='value'} for n,t in
          [('key','TEXT'),('culture','TEXT'),('value','REAL'),('flag','BOOLEAN')]]}

    def test_zero_blank_sentinel_and_culture_survive(self):
        rows=v.read_rows(self.path,self.schema)
        self.assertEqual([r['value'] for r in rows],['0','-1',''])
        self.assertEqual([r['culture'] for r in rows],['*','restricted','*'])

    def test_only_newline_conversion_is_accepted(self):
        expected=v.fingerprint(self.data)
        self.assertTrue(v.matches(self.data.replace(b'\n',b'\r\n'),expected))
        self.assertFalse(v.matches(self.data.replace(b',0,',b',1,'),expected))
        self.assertFalse(v.matches(self.data+b' ',expected))
        with self.assertRaises(ValueError):v.matches(b'a\rb',expected)

    def test_header_drift_rejected(self):
        self.path.write_bytes(self.data.replace(b'culture',b'culture_key'))
        with self.assertRaisesRegex(ValueError,'header drift'):v.read_rows(self.path,self.schema)

    def test_bad_boolean_and_nonfinite_rejected(self):
        for bad in [self.data.replace(b'true',b'True'),self.data.replace(b',0,',b',NaN,')]:
            self.path.write_bytes(bad)
            with self.assertRaises(ValueError):v.read_rows(self.path,self.schema)

    def test_duplicate_key_and_row_count_rejected(self):
        self.path.write_bytes(self.data.replace(b'b,restricted',b'a,*'))
        with self.assertRaisesRegex(ValueError,'duplicate key'):v.read_rows(self.path,self.schema)
        self.path.write_bytes(self.data)
        wrong=dict(self.schema,expected_rows=4)
        with self.assertRaisesRegex(ValueError,'expected 4'):v.read_rows(self.path,wrong)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):v.safe_path(self.root,'../elsewhere')

    def fixture(self):
        contract={'metadata_gates':[],'datasets':[self.schema],'joins':[],
                  'coverage_boundary':{'semantic_coverage':'partial'}}
        import hashlib
        lock={'source_commit':'synthetic-test-only','files':[dict(path='sample.csv',**v.fingerprint(self.data))],
              'contract_sha256':hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
        return lock,contract

    def test_integrated_verification_and_missing_file(self):
        lock,contract=self.fixture()
        self.assertEqual(v.verify(self.root,lock,contract)['status'],'passed')
        self.path.unlink()
        self.assertEqual(v.verify(self.root,lock,contract)['status'],'failed')

    def test_corrupt_source_rejected_existing_artifact_unchanged(self):
        lock,contract=self.fixture()
        artifact=self.root/'adviser.sqlite';artifact.write_bytes(b'prior artifact sentinel')
        self.path.write_bytes(self.data.replace(b',0,',b',99,'))
        self.assertEqual(v.verify(self.root,lock,contract)['status'],'failed')
        self.assertEqual(artifact.read_bytes(),b'prior artifact sentinel')

    def test_modified_contract_rejected(self):
        lock,contract=self.fixture();contract['datasets'][0]['expected_rows']=0
        self.assertEqual(v.verify(self.root,lock,contract)['status'],'failed')

    def test_failed_audit_gate_rejected(self):
        import hashlib
        lock,contract=self.fixture()
        self.root.joinpath('audit.json').write_text('{"status":"failed"}')
        lock['files'].append(dict(path='audit.json',**v.fingerprint(self.root.joinpath('audit.json').read_bytes())))
        contract['metadata_gates']=[{'path':'audit.json','keys':['status'],'equals':'passed'}]
        lock['contract_sha256']=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(v.verify(self.root,lock,contract)['status'],'failed')


if __name__=='__main__':unittest.main()
