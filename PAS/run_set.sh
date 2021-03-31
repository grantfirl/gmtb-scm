#!/bin/bash

set -u
#
#-----------------------------------------------------------------------
#
#
#
#-----------------------------------------------------------------------
#
base_case_name="$1"

log_file="log.run_set"
#
#-----------------------------------------------------------------------
#
# Cases using the PAS_GFS_v16beta-based suites.
#
#-----------------------------------------------------------------------
#
base_suite_name="PAS_GFS_v16beta"
resol_km_all=(      "25"      "13"       "3"        "3"        "3")
dt_sec_all=(       "300"     "180"      "40"       "40"       "40")
do_deep_conv_all=("true"    "true"    "true"    "false"    "false")
do_shal_conv_all=("true"    "true"    "true"     "true"    "false")

num_runs=${#resol_km_all[@]}

#for (( i=0; i<2; i++ )); do
for (( i=0; i<${num_runs}; i++ )); do

  do_deep_conv="${do_deep_conv_all[$i]}"
  do_shal_conv="${do_shal_conv_all[$i]}"
  resol_km="${resol_km_all[$i]}"
  dt_sec="${dt_sec_all[$i]}"

  printf "
========================================================================
Starting SCM run with new case...
========================================================================
"
# >& "${log_file}"

#  set -x
  pas_wrapper_run_gmtb_scm.sh \
    base_case_name="${base_case_name}" \
    base_suite_name="${base_suite_name}" \
    do_deep_conv="${do_deep_conv}" \
    do_shal_conv="${do_shal_conv}" \
    resol_km="${resol_km}" \
    dt_sec="${dt_sec}"
#  >& "${log_file}"
#  set +x

  printf "
========================================================================
Completed SCM run.
========================================================================
"
# >& log_file

done
#
#-----------------------------------------------------------------------
#
# Cases using the PAS_RRFS_v1alpha-based suites.
#
#-----------------------------------------------------------------------
#
base_suite_name="PAS_RRFS_v1alpha"
resol_km_all=(      "25"      "13"       "3"        "3"        "3"        "3")
dt_sec_all=(        "40"      "40"      "40"       "40"       "40"       "40")
do_deep_conv_all=("true"    "true"    "true"     "true"    "false"    "false")
do_shal_conv_all=("true"    "true"    "true"    "false"     "true"    "false")

num_runs=${#resol_km_all[@]}

for (( i=0; i<${num_runs}; i++ )); do

  do_deep_conv="${do_deep_conv_all[$i]}"
  do_shal_conv="${do_shal_conv_all[$i]}"
  resol_km="${resol_km_all[$i]}"
  dt_sec="${dt_sec_all[$i]}"

  printf "
========================================================================
Starting SCM run with new case...
========================================================================
"
# >& "${log_file}"

#  set -x
  pas_wrapper_run_gmtb_scm.sh \
    base_case_name="${base_case_name}" \
    base_suite_name="${base_suite_name}" \
    do_deep_conv="${do_deep_conv}" \
    do_shal_conv="${do_shal_conv}" \
    resol_km="${resol_km}" \
    dt_sec="${dt_sec}"
#  >& "${log_file}"
#  set +x

  printf "
========================================================================
Completed SCM run.
========================================================================
"
# >& log_file

done

