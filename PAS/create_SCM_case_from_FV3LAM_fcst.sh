#!/bin/bash

#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
# Save current shell options (in a global array).  Then set new options  
# for this script/function.                                              
#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
{ save_shell_opts; set -u +x; } > /dev/null 2>&1                       
#
#-----------------------------------------------------------------------
#
# Get the full path to the file in which this script/function is located
# (scrfunc_fp), the name of that file (scrfunc_fn), and the directory in
# which the file is located (scrfunc_dir).
#
#-----------------------------------------------------------------------
#
scrfunc_fp=$( readlink -f "${BASH_SOURCE[0]}" )
scrfunc_fn=$( basename "${scrfunc_fp}" )
scrfunc_dir=$( dirname "${scrfunc_fp}" )
#
#-----------------------------------------------------------------------
#
# Source bash utility functions.
#
#-----------------------------------------------------------------------
#
source ${scrfunc_dir}/source_util_funcs.sh

# This is an environment variable that 
# Some of the functions/scripts sourced by source_util.funcs.sh look for
# an environment variable named "VERBOSE" and, if "set -u" is being used, 
# will crash if it doesn't exist.  It would be good to modify these 
# functions/scripts so that the non-existence of VERBOSE doesn't make 
# them crash, even with "set -u".
VERBOSE="TRUE"
#
#-----------------------------------------------------------------------
#
# Source function used to obtain versions of the case name with and
# without a specified suffix.
#
#-----------------------------------------------------------------------
#
source ${scrfunc_dir}/get_case_name_wwo_suffix.sh
#
#-----------------------------------------------------------------------
#
# Specify the set of valid command line argument names for this script/
# function.  Then process the arguments provided to this script/function
# (which should consist of a set of name-value pairs of the form
# arg1="value1", etc).
#
#-----------------------------------------------------------------------
#
valid_args=( \
  "case_name" \
  "expt_dir" \
  "cdate" \
  "lon" \
  "lat" \
  )
set_args_cmd=$( process_args valid_args "$@" )
eval ${set_args_cmd}
#
#-----------------------------------------------------------------------
#
# For debugging purposes, print out values of arguments passed to this
# script.
#
#-----------------------------------------------------------------------
#
print_input_args valid_args
#
#-----------------------------------------------------------------------
#
# Make sure that the name of the SCM case to be generated ends with the
# required suffix.
#
#-----------------------------------------------------------------------
#
SCM_driver_suffix="_SCM_driver"

get_case_name_wwo_suffix \
  case_name="${case_name}" \
  suffix="${SCM_driver_suffix}" \
  output_varname_case_name_without_suffix="case_name_without_suffix" \
  output_varname_case_name_with_suffix="case_name_with_suffix" 

case_name_has_suffix="FALSE"
if [ "${case_name}" = "${case_name_with_suffix}" ]; then
  case_name_has_suffix="TRUE"
fi

if [ "${case_name_has_suffix}" = "FALSE" ]; then
  print_err_msg_exit "\
The specified case name (case_name) is missing the \"${SCM_driver_suffix}\" suffix.
The python script (UFS_IC_generator.py) called by this script to generate 
an SCM case from an FV3LAM forecast will use the the DEPHY international 
SCM format to generate the case data, and that requires the case name to
end in the \"${SCM_driver_suffix}\" suffix:
  case_name = \"${case_name}\""
fi
#
#-----------------------------------------------------------------------
#
# Set parameters that will be passed to the SCM case generator python
# script.
#
#-----------------------------------------------------------------------
#
cycle_dir="${expt_dir}/$cdate"
ics_dir="${cycle_dir}/INPUT"
grid_dir="${cycle_dir}/INPUT"
#
#-----------------------------------------------------------------------
#
# Set the base directory in which the SCM code has been cloned as well
# as the full path to the "scripts" subdirectory containing the python
# script used to generate a new SCM case from an FV3LAM run.
#
#-----------------------------------------------------------------------
#
scm_basedir=$( readlink -f "${scrfunc_dir}/../" )
scripts_dir="${scm_basedir}/scm/etc/scripts"
#
#-----------------------------------------------------------------------
#
# Run the case generator script.
#
#-----------------------------------------------------------------------
#
cd "${scripts_dir}"

./UFS_IC_generator.py \
  -l "$lon" "$lat" \
  -i "${ics_dir}" \
  -g "${grid_dir}" \
  -f "${cycle_dir}" \
  -n "${case_name_with_suffix}" \
  -lam \
  -sc
#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
# Restore the shell options saved at the beginning of this script/function.
#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
{ restore_shell_opts; } > /dev/null 2>&1                               

