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

load("@my_deps//:requirements.bzl", "requirement")

package(
    default_visibility = ["//visibility:public"],
)

# Build rules for DeID evaluation tools.

licenses(["notice"])  # Apache License 2.0

py_binary(
    name = "upload_files_to_bq",
    srcs = ["upload_files_to_bq.py"],
    deps = [
        "//common:gcsutil",
        requirement("apache_beam"),
        requirement("google-cloud-storage"),
    ],
)

py_binary(
    name = "remove_invalid_characters",
    srcs = ["remove_invalid_characters.py"],
    deps = [
        "//common:mae",
    ],
)
