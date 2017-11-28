# Copyright 2017 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for google3.third_party.py.eval.run_pipeline_lib."""

from __future__ import absolute_import

import math
import unittest

from common import testutil
from eval import results_pb2
from eval import run_pipeline_lib
from mock import patch

from google.protobuf import descriptor
from google.protobuf import text_format


xml_template = """<?xml version="1.0" encoding="UTF-8" ?>
<InspectPhiTask>
<TEXT><![CDATA[word1   w2 w3  wrd4 5 word6   word7 multi token entity]]></TEXT>
<TAGS>
{0}
</TAGS></InspectPhiTask>
"""

tag_template = '<{0} id="{0}0" spans="{1}~{2}" />'


def normalize_floats(pb):
  for desc, values in pb.ListFields():
    is_repeated = True
    if desc.label is not descriptor.FieldDescriptor.LABEL_REPEATED:
      is_repeated = False
      values = [values]

    normalized_values = None
    if desc.type == descriptor.FieldDescriptor.TYPE_FLOAT:
      normalized_values = [round(x, 6) for x in values]

    if normalized_values is not None:
      if is_repeated:
        pb.ClearField(desc.name)
        getattr(pb, desc.name).extend(normalized_values)
      else:
        setattr(pb, desc.name, normalized_values[0])

    if desc.type == descriptor.FieldDescriptor.TYPE_MESSAGE:
      for v in values:
        normalize_floats(v)
  return pb


class RunPipelineLibTest(unittest.TestCase):

  @patch('google.cloud.storage.Client')
  def testE2E(self, fake_client_fn):
    input_pattern = 'gs://bucketname/input/*'
    golden_dir = 'gs://bucketname/goldens'
    results_dir = 'gs://bucketname/results'
    storage_client = testutil.FakeStorageClient()
    fake_client_fn.return_value = storage_client

    tp_tag = tag_template.format('TypeA', 0, 5)
    fp_tag = tag_template.format('TypeA', 8, 10)
    fn_tag = tag_template.format('TypeA', 11, 13)
    fn2_tag = tag_template.format('TypeA', 15, 19)
    findings_tags = '\n'.join([tp_tag, fp_tag])
    golden_tags = '\n'.join([tp_tag, fn_tag, fn2_tag])
    testutil.set_gcs_file('bucketname/input/file.xml',
                          xml_template.format(findings_tags))
    testutil.set_gcs_file('bucketname/goldens/file.xml',
                          xml_template.format(golden_tags))

    tp2_tag = tag_template.format('TypeB', 20, 21)
    # False negative + false positive for entity matching, but true positive for
    # binary token matching.
    entity_fp_tag = tag_template.format('TypeX', 30, 35)
    entity_fn_tag = tag_template.format('TypeY', 30, 35)
    # Two tokens are tagged as one in the golden. This is not a match for entity
    # matching, but is two matches for binary token matching.
    partial_tag1 = tag_template.format('TypeA', 36, 41)
    partial_tag2 = tag_template.format('TypeA', 42, 47)
    partial_tag3 = tag_template.format('TypeA', 48, 54)
    multi_token_tag = tag_template.format('TypeA', 36, 54)
    findings_tags = '\n'.join([tp_tag, tp2_tag, entity_fp_tag, partial_tag1,
                               partial_tag2, partial_tag3])
    golden_tags = '\n'.join([tp_tag, tp2_tag, entity_fn_tag, multi_token_tag])
    testutil.set_gcs_file('bucketname/input/file2.xml',
                          xml_template.format(findings_tags))
    testutil.set_gcs_file('bucketname/goldens/file2.xml',
                          xml_template.format(golden_tags))
    run_pipeline_lib.run_pipeline(input_pattern, golden_dir, results_dir,
                                  'credentials', 'project', pipeline_args=None)

    expected_text = """strict_entity_matching_results {
  micro_average_results {
    true_positives: 3
    false_positives: 5
    false_negatives: 4
    precision: 0.375
    recall: 0.428571
    f_score: 0.4
  }
  macro_average_results {
    precision: 0.416667
    recall: 0.416667
    f_score: 0.416667
  }
}
binary_token_matching_results {
  micro_average_results {
    true_positives: 7
    false_positives: 1
    false_negatives: 2
    precision: 0.875
    recall: 0.777778
    f_score: 0.823529
  }
  macro_average_results {
    precision: 0.75
    recall: 0.666667
    f_score: 0.705882
  }
}"""
    expected_results = results_pb2.Results()
    text_format.Merge(expected_text, expected_results)
    results = results_pb2.Results()
    text_format.Merge(
        testutil.get_gcs_file('bucketname/results/aggregate_results.txt'),
        results)
    self.assertEqual(normalize_floats(expected_results),
                     normalize_floats(results))

  def testHMean(self):
    self.assertAlmostEqual(2.0, run_pipeline_lib.hmean(1, 2, 4, 4))
    self.assertTrue(math.isnan(run_pipeline_lib.hmean(0, 1, 2)))

  def testCalculateStats(self):
    stats = results_pb2.Stats()
    stats.true_positives = 12
    stats.false_positives = 8
    stats.false_negatives = 3
    run_pipeline_lib.calculate_stats(stats)
    self.assertAlmostEqual(.6, stats.precision)
    self.assertAlmostEqual(.8, stats.recall)
    self.assertAlmostEqual(.6857142857142856, stats.f_score)

    stats = results_pb2.Stats()
    run_pipeline_lib.calculate_stats(stats)
    self.assertTrue(math.isnan(stats.precision))
    self.assertTrue(math.isnan(stats.recall))
    self.assertTrue(math.isnan(stats.f_score))
    self.assertEqual(
        'Precision has denominator of zero. Recall has denominator of zero. '
        'f-score is NaN',
        stats.error_message)

  def testMacroStats(self):
    macro_stats = run_pipeline_lib._MacroStats()
    macro_stats.count = 50
    macro_stats.precision_sum = 40
    macro_stats.recall_sum = 45

    stats = macro_stats.calculate_stats()
    self.assertAlmostEqual(.8, stats.precision)
    self.assertAlmostEqual(.9, stats.recall)
    self.assertAlmostEqual(.8470588235294118, stats.f_score)

    macro_stats = run_pipeline_lib._MacroStats()
    stats = macro_stats.calculate_stats()
    self.assertTrue(math.isnan(stats.precision))
    self.assertTrue(math.isnan(stats.recall))
    self.assertTrue(math.isnan(stats.f_score))

  def testTokenizeSet(self):
    finding = run_pipeline_lib.Finding
    findings = set([finding('TYPE_A', 0, 2, 'hi'),
                    finding('TYPE_A', 4, 14, 'two tokens'),
                    finding('TYPE_A', 20, 38, 'three\tmore  tokens')])
    tokenized = run_pipeline_lib.tokenize_set(findings)
    expected_tokenized = set([finding(None, 0, 2, 'hi'),
                              finding(None, 4, 7, 'two'),
                              finding(None, 8, 14, 'tokens'),
                              finding(None, 20, 25, 'three'),
                              finding(None, 26, 30, 'more'),
                              finding(None, 32, 38, 'tokens')])
    self.assertEqual(expected_tokenized, tokenized)

  def testInvalidSpans(self):
    with self.assertRaises(Exception):
      run_pipeline_lib.Finding.from_tag('invalid', '4~2', 'full text')
    with self.assertRaises(Exception):
      run_pipeline_lib.Finding.from_tag('out_of_range', '0~10', 'full text')

if __name__ == '__main__':
  unittest.main()