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
  "base_case_name" \
  "base_suite_name" \
  "do_deep_conv" \
  "do_shal_conv" \
  "resol_km" \
  "dt_sec" \
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
# Set list of valid values for each input parameter.
#
#-----------------------------------------------------------------------
#
valid_vals_base_case_name=( \
"arm_sgp_summer_1997_A" \
"arm_sgp_summer_1997_B" \
"arm_sgp_summer_1997_C" \
"arm_sgp_summer_1997_R" \
"arm_sgp_summer_1997_S" \
"arm_sgp_summer_1997_T" \
"arm_sgp_summer_1997_U" \
"arm_sgp_summer_1997_X" \
"twpice" \
"my_case_01_SCM_driver" \
"my_case_02_SCM_driver" \
"my_case_03_SCM_driver" \
"my_case_04_SCM_driver" \
)

valid_vals_base_suite_name=( \
"PAS_GFS_v16beta" \
"PAS_RRFS_v1alpha" \
)

valid_vals_do_deep_conv=( \
"TRUE" \
"true" \
"FALSE" \
"false" \
)

valid_vals_do_shal_conv=( \
"TRUE" \
"true" \
"FALSE" \
"false" \
)

valid_vals_resol_km=( \
"25" \
"13" \
"3" \
)
#
#-----------------------------------------------------------------------
#
# Check that the input parameters to this script are set to valid values.
#
#-----------------------------------------------------------------------
#
check_var_valid_value "base_case_name" "valid_vals_base_case_name"
check_var_valid_value "base_suite_name" "valid_vals_base_suite_name"
check_var_valid_value "do_deep_conv" "valid_vals_do_deep_conv"
check_var_valid_value "do_shal_conv" "valid_vals_do_shal_conv"
check_var_valid_value "resol_km" "valid_vals_resol_km"
#
#-----------------------------------------------------------------------
#
# For convenience, change the "boolean" arguments do_deep_conv and 
# do_shal_conv to upper case.
#
#-----------------------------------------------------------------------
#
do_deep_conv="${do_deep_conv^^}"
do_shal_conv="${do_shal_conv^^}"
#
#-----------------------------------------------------------------------
#
# Set the name of the scm executable, the physics suite name, and some 
# of the physics suite namelist parameters according to the command line
# arguments to this script.
#
#-----------------------------------------------------------------------
#
if [ "${base_suite_name}" = "PAS_GFS_v16beta" ]; then

  scm_exec_fn="gmtb_scm_ideep_1"

  if [ "${do_deep_conv}" = "TRUE" ] && \
     [ "${do_shal_conv}" = "TRUE" ]; then

    suite_name="${base_suite_name}"
    conv_suffix="deepSAMF_on_shalSAMF_on"

    do_deep=".true."
    imfdeepcnv="2"
    shal_cnv=".true."
    imfshalcnv="2"

  elif [ "${do_deep_conv}" = "TRUE" ] && \
       [ "${do_shal_conv}" = "FALSE" ]; then

    print_err_msg_exit "\
The following combination of base suite (base_suite_name) and deep and
shallow convection flags (do_deep_conv and do_shal_conv) has not yet been 
implemented in this PAS version of the SCM: 
  base_suite_name = \"${base_suite_name}\"
  do_deep_conv = \"${do_deep_conv}\"
  do_shal_conv = \"${do_shal_conv}\""

#    suite_name="${base_suite_name}_no_shalcu"
#    conv_suffix="deepSAMF_on_shalSAMF_off"
#
#    do_deep=".true."
#    imfdeepcnv="2"
#    shal_cnv=".false."
#    imfshalcnv="-1"

  elif [ "${do_deep_conv}" = "FALSE" ] && \
       [ "${do_shal_conv}" = "TRUE" ]; then

    suite_name="${base_suite_name}_no_deepcu"
    conv_suffix="deepSAMF_off_shalSAMF_on"

    do_deep=".false."
    imfdeepcnv="-1"
    shal_cnv=".true."
    imfshalcnv="2"

  elif [ "${do_deep_conv}" = "FALSE" ] && \
       [ "${do_shal_conv}" = "FALSE" ]; then

    suite_name="${base_suite_name}_no_cumulus"
    conv_suffix="deepSAMF_off_shalSAMF_off"

    do_deep=".false."
    imfdeepcnv="-1"
    shal_cnv=".false."
    imfshalcnv="-1"

  fi

elif [ "${base_suite_name}" = "PAS_RRFS_v1alpha" ]; then

  if [ "${do_deep_conv}" = "TRUE" ] && \
     [ "${do_shal_conv}" = "TRUE" ]; then

    suite_name="${base_suite_name}_cumulus"
    conv_suffix="deepGF_on_shalGF_on"
    scm_exec_fn="gmtb_scm_ideep_1"

    do_deep=".true."
    imfdeepcnv="3"
    shal_cnv=".true."
    imfshalcnv="3"

  elif [ "${do_deep_conv}" = "TRUE" ] && \
       [ "${do_shal_conv}" = "FALSE" ]; then

    suite_name="${base_suite_name}_cumulus"
    conv_suffix="deepGF_on_shalGF_off"
    scm_exec_fn="gmtb_scm_ideep_1"

    do_deep=".true."
    imfdeepcnv="3"
    shal_cnv=".false."
    imfshalcnv="-1"

  elif [ "${do_deep_conv}" = "FALSE" ] && \
       [ "${do_shal_conv}" = "TRUE" ]; then

# This case crashed.  Not sure why.  It's the only one that uses the 
# "gmtb_scm_ideep_0" executable, so that might be related.

    suite_name="${base_suite_name}_cumulus"
    conv_suffix="deepGF_off_shalGF_on"
    scm_exec_fn="gmtb_scm_ideep_0"

    do_deep=".false."
    imfdeepcnv="-1"
    shal_cnv=".true."
    imfshalcnv="3"

  elif [ "${do_deep_conv}" = "FALSE" ] && \
       [ "${do_shal_conv}" = "FALSE" ]; then

    suite_name="${base_suite_name}"
    conv_suffix="deepGF_off_shalGF_off"
    scm_exec_fn="gmtb_scm_ideep_1"

    do_deep=".false."
    imfdeepcnv="-1"
    shal_cnv=".false."
    imfshalcnv="-1"

  fi

fi
#
#-----------------------------------------------------------------------
#
# Set the base directory in which the SCM code has been cloned as well
# as the full path to the "bin" subdirectory containing executables, 
# python scripts for running the SCM, and links to other scripts.
#
#-----------------------------------------------------------------------
#
scm_basedir=$( readlink -f "${scrfunc_dir}/../" )
bin_dir="${scm_basedir}/scm/bin"
#
#-----------------------------------------------------------------------
#
# Create a namelist file for the physics suite by replacing values in a 
# template namelist file associated with the suite.
#
#-----------------------------------------------------------------------
#
# Set the names of and full paths to the template and actual namelist 
# files.
#
suite_nml_dir="${scm_basedir}/ccpp/physics_namelists"

tmpl_suite_nml_fn="tmpl.input_${base_suite_name}_etc.nml"
suite_nml_fn="input_${suite_name}.nml"

tmpl_suite_nml_fp="${suite_nml_dir}/${tmpl_suite_nml_fn}"
suite_nml_fp="${suite_nml_dir}/${suite_nml_fn}"
#
# Make sure that the template physics suite namelist file exists.
#
if [ ! -f "${tmpl_suite_nml_fp}" ]; then
  print_err_msg_exit "\
The template physics suite namelist file (tmpl_suite_nml_fp) for this 
base suite (base_suite_name) does not exist:
  base_suite_name = \"${base_suite_name}\"
  tmpl_suite_nml_fp = \"${tmpl_suite_nml_fp}\"
Please create such a template file and rerun."
fi
#
# Copy the template suite namelist file into the actual suite namelist 
# file.
#
print_info_msg "
Copying the template suite namelist file to the actual suite namelist file:
  tmpl_suite_nml_fp = \"${tmpl_suite_nml_fp}\"
  suite_nml_fp = \"${suite_nml_fp}\"
"
cp "${tmpl_suite_nml_fp}" "${suite_nml_fp}"
#
# Use the sed utility to replace the placeholder value for cdmbgwd in the 
# namelist file with an actual value.  Note the this value depends on the 
# resolution used for the SCM run (which is passed to this script as a
# command line argument).
#
regex_search="(^\s*cdmbgwd\s*=\s*)(<.*>)\s*$"
case "${resol_km}" in
  "25") regex_replace="\1""1.1, 0.72, 1.0, 1.0"
        ;;
  "13") regex_replace="\1""4.0, 0.15, 1.0, 1.0"
        ;;
   "3") regex_replace="\1""0.88, 0.04, 1.0, 1.0"
        ;;
     *) print_err_msg_exit "\
A set of values for the physics namelist parameter cdmbgwd has not been 
specified for the given resolution (resol_km):
  resol_km = \"${resol_km}\"
Stopping."
        ;;
esac

sed -i -r -e "s|${regex_search}|${regex_replace}|" "${suite_nml_fp}" || \
  print_err_msg_exit "\
Attempt to replace the placeholder value of \"cdmbgwd\" in the suite namelist
file (suite_nml_fp) using the sed utility failed:
  suite_nml_fp = \"${suite_nml_fp}\""
#
# Use the sed utility to replace the placeholder values for do_deep,
# imfdeepcnv, imfshalcnv, and shal_cnv in the physics namelist file with 
# actual values.
#
params=("do_deep" "imfdeepcnv" "shal_cnv" "imfshalcnv")
for param in "${params[@]}"; do
  regex_search="(^\s*$param\s*=\s*)(<.*>)\s*$"
  regex_replace="\1""${!param}"
  sed -i -r -e "s|${regex_search}|${regex_replace}|" "${suite_nml_fp}" || \
    print_err_msg_exit "\
Attempt to replace the placeholder value of \"$param\" in the suite namelist
file (suite_nml_fp) using the sed utility failed:
  suite_nml_fp = \"${suite_nml_fp}\""
done
#
#-----------------------------------------------------------------------
#
# Get the counterparts of the base case name with and without the suffix
# "_SCM_driver".  Then set a flag that specifies whether or not the base
# case name passed to this script ends with the suffix.
#
#-----------------------------------------------------------------------
#
SCM_driver_suffix="_SCM_driver"

get_case_name_wwo_suffix \
  case_name="${base_case_name}" \
  suffix="${SCM_driver_suffix}" \
  output_varname_case_name_without_suffix="base_case_name_without_suffix" \
  output_varname_case_name_with_suffix="base_case_name_with_suffix"

base_case_name_has_suffix="FALSE"
if [ "${base_case_name}" = "${base_case_name_with_suffix}" ]; then
  base_case_name_has_suffix="TRUE"
fi
#
#-----------------------------------------------------------------------
#
# Construct the case name that will be passed to the python SCM run script.  
# We do not include the physics suite in this because that script will
# automatically append it to the case name to obtain directory names, 
# etc.
#
#-----------------------------------------------------------------------
#
case_name_without_suffix="${base_case_name_without_suffix}_dx_${resol_km}km_dt_${dt_sec}sec_${conv_suffix}"
case_name_with_suffix="${case_name_without_suffix}${SCM_driver_suffix}"
#
#-----------------------------------------------------------------------
#
# Generate the case namelist file by replacing placeholders in a template 
# namelist file with actual values.  Template namelist files exist only 
# for the base cases, so the name of the template file must be constructed
# using base_case_name.  
#
# Note that the name of the actual case namelist file must constructed 
# using the case name without the "_SCM_driver" suffix whether or not the
# specified base_case contains that suffix.  That is because the python 
# script run_gmtb_scm.py called below to run the SCM takes in the case 
# name without a suffix, and it does not append the suffix when constucting 
# the name of the case namelist file to read in.  [However, it does append 
# the suffix to the name of the NetCDF file containing processed case 
# data if input_type in the namelist file is set to 1 (meaning that the
# data is in the DEPHY international SCM format, which in turn means that 
# the case name must end in the "_SCM_driver" suffix), so the name of the 
# symlink created below that points to the processed case data file must 
# include the suffix; see below). 
#
#-----------------------------------------------------------------------
#
case_nml_dir="${scm_basedir}/scm/etc/case_config"

tmpl_case_nml_fn="tmpl.${base_case_name}.nml"
case_nml_fn="${case_name_without_suffix}.nml"

tmpl_case_nml_fp="${case_nml_dir}/${tmpl_case_nml_fn}"
case_nml_fp="${case_nml_dir}/${case_nml_fn}"
#
# Make sure that the template case namelist file exists.
#
if [ ! -f "${tmpl_case_nml_fp}" ]; then
  print_err_msg_exit "\
The template SCM case namelist file (tmpl_case_nml_fp) for this base case 
(base_case_name) does not exist:
  base_case_name = \"${base_case_name}\"
  tmpl_case_nml_fp = \"${tmpl_case_nml_fp}\"
Please create such a template file and rerun."
fi
#
# Copy the template case namelist file to the actual case namelist file.
#
print_info_msg "
Copying the template case namelist file to the actual case namelist file:
  tmpl_case_nml_fp = \"${tmpl_case_nml_fp}\"
  case_nml_fp = \"${case_nml_fp}\"
"

cp "${tmpl_case_nml_fp}" "${case_nml_fp}"
#
# Set the case name in the case namelist file.
#
regex_search="(^\s*case_name\s*=\s*)(<.*>)(,)\s*$"
regex_replace="\1""\'${case_name_without_suffix}\'""\3"
sed -i -r -e "s|${regex_search}|${regex_replace}|" "${case_nml_fp}"
#
# Set the time step in the case namelist file.
#
regex_search="(^\s*dt\s*=\s*)(<.*>)(,)\s*$"
regex_replace="\1""${dt_sec}""\3"
sed -i -r -e "s|${regex_search}|${regex_replace}|" "${case_nml_fp}"
#
# Set the column area in the case namelist file.
#
resol_m=$( bc -l <<< "${resol_km}*1000" )
column_area_m2=$( bc -l <<< "${resol_m}*${resol_m}" )

regex_search="(^\s*column_area\s*=\s*)(<.*>)(,)\s*$"
regex_replace="\1""${column_area_m2}""\3"
sed -i -r -e "s|${regex_search}|${regex_replace}|" "${case_nml_fp}"
#
#-----------------------------------------------------------------------
#
# Create a symlink that points to the processed case input data file (in
# NetCDF format) that the case should use.
#
# The existing processed case data files are for the base cases.  Thus,
# the name of the target of the link must be constructed using base_case_name.
# The name of the symlink must be constructed using the case name (either
# with or without the "_SCM_driver" suffix depending on whther or not 
# base_case_name contains the suffix) because the python script run_gmtb_scm.py 
# called below to run the SCM takes as an argument the case name without 
# a suffix, not base_case_name, and it then constructs the name of the
# processed case data file such that the latter ends with the suffix if
# base_case_name ends with the suffix (or, equivalently, if the variable 
# input_type in the case namelist file is set to 1, meaning that the data 
# is in the DEPHY international SCM format, which in turn means that the 
# case name should end in the "_SCM_driver" suffix) and not otherwise.
#
#-----------------------------------------------------------------------
#
processed_case_input_dir="${scm_basedir}/scm/data/processed_case_input"
target="${processed_case_input_dir}/${base_case_name}.nc"
if [ "${base_case_name_has_suffix}" = "TRUE" ]; then
  symlink="${processed_case_input_dir}/${case_name_with_suffix}.nc"
else
  symlink="${processed_case_input_dir}/${case_name_without_suffix}.nc"
fi
ln -fs --relative "${target}" "${symlink}"
#
#-----------------------------------------------------------------------
#
# Create a symlink to the appropriate SCM executable file.
#
#-----------------------------------------------------------------------
#
target="${bin_dir}/${scm_exec_fn}"
symlink="${bin_dir}/gmtb_scm"
ln -fs --relative "${target}" "${symlink}"
#
#-----------------------------------------------------------------------
#
# Set the full path to the experiment directory.  Then check if it already
# exists and if so, deal with it as specified by preexisting_dir_method. 
#
#-----------------------------------------------------------------------
#
output_subdir="output_${case_name_without_suffix}_${suite_name}"
output_dir="${bin_dir}/${output_subdir}"
preexisting_dir_method="rename"  # Other possibilites are "delete" and "quit".
check_for_preexist_dir_file "${output_dir}" "${preexisting_dir_method}"
#
#-----------------------------------------------------------------------
#
# Call the python script that runs the SCM case with the specified case
# and physics suite.  Note that we have to pass in the case name without
# a suffix because this script will add the suffix if necessary.
#
#-----------------------------------------------------------------------
#
./run_gmtb_scm.py -c ${case_name_without_suffix} -s ${suite_name}
#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
# Restore the shell options saved at the beginning of this script/function.
#                                                                        
#----------------------------------------------------------------------- 
#                                                                        
{ restore_shell_opts; } > /dev/null 2>&1                               

