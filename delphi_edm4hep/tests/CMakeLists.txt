# Tests for delphi_edm4hep. Minimal but real: validate the CLI argument
# contract (the -n parser + required-arg checks). A full conversion test suite
# over real bank data is future work; these guard the arg-parsing the binaries
# promise and replace the old S1 echo placeholder.
#
# Each CLI must REJECT (exit nonzero) on missing args and on a non-numeric or
# non-positive -n. WILL_FAIL inverts the verdict, so the test passes iff the CLI
# exits nonzero. These exit during arg parsing, before any file is opened, so no
# data files are needed.
add_test(NAME cli_sdst_rejects_no_args COMMAND delphi_sdst_pass)
add_test(NAME cli_sdst_rejects_bad_n   COMMAND delphi_sdst_pass in.sdst out.edm4hep.root -n abc)
add_test(NAME cli_sdst_rejects_zero_n  COMMAND delphi_sdst_pass in.sdst out.edm4hep.root -n 0)
add_test(NAME cli_fdst_rejects_no_args COMMAND delphi_fdst_pass)
add_test(NAME cli_fdst_rejects_bad_n   COMMAND delphi_fdst_pass a.root in.fadana out.edm4hep.root -n abc)

set_tests_properties(
  cli_sdst_rejects_no_args
  cli_sdst_rejects_bad_n
  cli_sdst_rejects_zero_n
  cli_fdst_rejects_no_args
  cli_fdst_rejects_bad_n
  PROPERTIES WILL_FAIL TRUE
)

# Alignment / relation audit: regression guard for the bug class where a
# UserData array is mislabelled as parallel to the wrong collection (e.g.
# per-particle vs per-track), or a relation (RecDqdx -> Track) is left unset.
# Runs align_audit.py against the EDM4hep file named in DELPHI_EDM4HEP_SAMPLE;
# with no sample set the script exits 0 (skip), so this is a no-op until CI
# points it at a converted file. Needs Python3 + podio (the key4hep view).
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_FOUND)
  add_test(NAME alignment_audit
           COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/align_audit.py)
endif()
