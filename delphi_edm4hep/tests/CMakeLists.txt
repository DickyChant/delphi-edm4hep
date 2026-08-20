# Tests for delphi_edm4hep. A full conversion test suite over real bank data
# is future work.
#
# Each pass must print its usage message when run with no arguments. Matching
# the usage text rather than just a nonzero exit also proves the binary loaded
# its shared libraries and reached main(). No data files are needed.
add_test(NAME cli_sdst_rejects_no_args COMMAND delphi_sdst_pass)
add_test(NAME cli_fdst_rejects_no_args COMMAND delphi_fdst_pass)
set_tests_properties(cli_sdst_rejects_no_args
  PROPERTIES PASS_REGULAR_EXPRESSION "usage: .*input\\.sdst")
set_tests_properties(cli_fdst_rejects_no_args
  PROPERTIES PASS_REGULAR_EXPRESSION "usage: .*input\\.fadana")

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
