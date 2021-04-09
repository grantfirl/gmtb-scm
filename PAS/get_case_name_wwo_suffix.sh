#
#-----------------------------------------------------------------------
#
# This file defines a function that takes a specified SCM case name and 
# returns two possibly modified case names:
#
#
#-----------------------------------------------------------------------
#
function get_case_name_wwo_suffix() {
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
  local scrfunc_fp=$( readlink -f "${BASH_SOURCE[0]}" )
  local scrfunc_fn=$( basename "${scrfunc_fp}" )
  local scrfunc_dir=$( dirname "${scrfunc_fp}" )
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
# Get the name of this function.
#
#-----------------------------------------------------------------------
#
  local func_name="${FUNCNAME[0]}"
#
#-----------------------------------------------------------------------
#
# Specify the set of valid argument names for this script/function.  Then
# process the arguments provided to this script/function (which should
# consist of a set of name-value pairs of the form arg1="value1", etc).
#
#-----------------------------------------------------------------------
#
  local valid_args=( \
"case_name" \
"suffix" \
"output_varname_case_name_without_suffix" \
"output_varname_case_name_with_suffix" \
  )
  local set_args_cmd=$( process_args valid_args "$@" )
  eval ${set_args_cmd}
#
#-----------------------------------------------------------------------
#
# For debugging purposes, print out values of arguments passed to this
# script.  Note that these will be printed out only if VERBOSE is set to
# TRUE.
#
#-----------------------------------------------------------------------
#
  print_input_args valid_args
#
#-----------------------------------------------------------------------
#
# Declare local variables.
#
#-----------------------------------------------------------------------
#
  local __len_suffix \
        __len_case_name \
        __len_case_name_without_suffix \
        __case_name_suffix \
        __case_name_without_suffix \
        __case_name_with_suffix
#
#-----------------------------------------------------------------------
#
# Make sure the specified case name is not empty.
#
#-----------------------------------------------------------------------
#
  if [ -z "${case_name}" ]; then
    print_err_msg_exit "\
The case name (case_name) cannot be empty:
  case_name = \"${case_name}\"
Please specify a non-empty case name and rerun."
  fi
#
#-----------------------------------------------------------------------
#
# Set __case_name_suffix as follows.  If case_name is shorter than suffix,
# then set __case_name_suffix to case_name.  Otherwise, set it to the 
# last __len_suffix characters of case_name, where __len_suffix is the 
# number of characters in suffix. 
#
#-----------------------------------------------------------------------
#
  __len_suffix="${#suffix}"
  __len_case_name="${#case_name}"

  __case_name_suffix="${case_name}"
  if [ "${__len_case_name}" -gt "${__len_suffix}" ]; then
    __case_name_suffix=${case_name: -${__len_suffix}}
  fi
#
#-----------------------------------------------------------------------
#
# Consider the case in which the last __len_suffix characters of case_name
# are not equal to suffix, or the case in which case_name is shorter than
# suffix.  In these cases, set the case name without suffix to case_name, 
# and set the case name with suffix to case_name with suffix appended.
#
#-----------------------------------------------------------------------
#
  if [ "${__case_name_suffix}" != "${suffix}" ]; then

    print_info_msg "
The case name (case_name) does not end with the specified suffix (suffix):
  case_name = \"${case_name}\"
  suffix = \"${suffix}\"
Appending that string to case_name in order to obtain the counterpart of
the case name that includes the suffix.
"

    __case_name_without_suffix="${case_name}"
    __case_name_with_suffix="${case_name}${suffix}"
#
#-----------------------------------------------------------------------
#
# Consider the case in which the last __len_suffix characters of case_name
# are equal to suffix.  This has sub-cases.
#
#
#-----------------------------------------------------------------------
#
  else
#
# case_name ends with suffix but is not exactly equal to suffix.  In this
# case, set the case name with suffix to case_name, and get the case namne
# without suffix by removing the suffix from the end of case_name.
#
    if [ "${__len_case_name}" -ne "${__len_suffix}" ]; then

      print_info_msg "
The case name (case_name) ends with the specified suffix (suffix):
  case_name = \"${case_name}\"
  suffix = \"${suffix}\"
Removing the suffix from the end of case_name in order to obtain the 
counterpart of the case name without the suffix.
"

      __len_case_name_without_suffix=$(( ${__len_case_name} - ${__len_suffix} ))
      __case_name_without_suffix="${case_name:0:${__len_case_name_without_suffix}}"
      __case_name_with_suffix="${case_name}"
#
# case_name ends with suffix and contains no other (preceeding) characters, 
# i.e. it is exactly equal to suffix.  In this case, print out an error 
# message and exit because if we were to strip out the suffix from case_name, 
# the resulting name without suffix would be a null string, and that 
# wouldn't work.
#
    else

      print_err_msg_exit "\
The case name (case_name) cannot be exactly equal to the specified suffix;
it must contain other preceeding characters:
  case_name = \"${case_name}\"
  suffix = \"${suffix}\"
Please specify a case name that contains one or more characters before
\"${suffix}\" and rerun."

    fi

  fi
#
#-----------------------------------------------------------------------
#
# Set output variables.
#
#-----------------------------------------------------------------------
#
  eval ${output_varname_case_name_without_suffix}="${__case_name_without_suffix}"
  eval ${output_varname_case_name_with_suffix}="${__case_name_with_suffix}"
#
#-----------------------------------------------------------------------
#
# Restore the shell options saved at the beginning of this script/function.
#
#-----------------------------------------------------------------------
#
  { restore_shell_opts; } > /dev/null 2>&1

}

