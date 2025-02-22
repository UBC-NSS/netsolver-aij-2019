#!/usr/bin/env python3
import os
import itertools
import tempfile
import sys

# TODO(nodir): pass these variables as a runtime parameter
MAIN_PATH = '../../..'
CPU_TIME_LIMIT = 3600 # seconds
RAM_LIMIT = 80000 # 80 GB

runlim_tmp = tempfile.mktemp()


if len(sys.argv)>1:
  fmcad_modes=[sys.argv[1]]
  print("Running fmcadZ3 on modes " + str(fmcad_modes))
  summary=open("fmcad13_z3_%s_summary.txt"%(sys.argv[1]),"w")
  runlim_log="fmcad13_z3_%s_runlim.txt"%(sys.argv[1])
else:
  fmcad_modes=["4","3","1"] #According to Yifei (thanks!), mode 1 reproduces the unoptimized CNF encoding from their paper, mode 3 reproduces the optimized abstraction-refinement encoding; setting 4 isn't in the paper but appears to work better than the others, so I include it as well.
  summary=open("fmcad13_z3_summary.txt","w")
  runlim_log="fmcad13_z3_runlim.txt"
log = open(runlim_log,'w')
print("Logging results to " + runlim_tmp)
runlim_settings=" -t {} -s {} -o {}".format(CPU_TIME_LIMIT, RAM_LIMIT, runlim_tmp)

  
#Note: Secondnet, FMCAD, and VDCMapper all take different file formats, which is a pain.
#I have instrumented all three to output logs of the time required for each instance.
fmcad_file_location=os.path.join(MAIN_PATH, "instances/fmcad/")

fmcad_datacenters=["tree_200.20","tree16_200.20","tree16_400.20","tree16_2000.20"]
fmcad_vdcs=["vn2_3.1","vn2_3.2","vn2_3.3","vn2_5.1","vn2_5.2","vn2_5.3"]


summary.write("#Solver\tDatacenter\tVDC\tNAllocated\tRuntime\n")
summary.flush()
if not os.path.exists("timelogs"):
    os.makedirs("timelogs")
if not os.path.exists("correctness_logs"):
    os.makedirs("correctness_logs")    
for mode,datacenter,instance in itertools.product(fmcad_modes,fmcad_datacenters,fmcad_vdcs):
  print( datacenter + " " + instance + " " + mode)
  #Using Armin Biere's runlim to limit runtimes, available from http://fmv.jku.at/runlim/
  instance_log="timelogs/fmcad13_z3_mode%s_datacenter%s_instance_%s.log"%(mode,datacenter,instance)
  instance_correctness_log="correctness_logs/fmcad13_z3_mode%s_datacenter%s_instance_%s.log"%(mode,datacenter,instance)
  if  os.path.exists(instance_log):
    os.remove(instance_log)
  if  os.path.exists(instance_correctness_log):
    os.remove(instance_correctness_log)     
  command="runlim " + runlim_settings + " " + os.path.join(MAIN_PATH, "solvers/mainz3 ") + fmcad_file_location + datacenter + " " +fmcad_file_location + instance + " " + mode + " " + instance_log + " " + instance_correctness_log
  print("Running: " + command) 
  code = os.system(command)
  runtime=-1
  nvms=-1
  try:
    timefile = open(instance_log)
    for line in timefile:
      if line.startswith("#") or line.startswith("init"):
        continue
      if line.startswith("done"):
        #Get runtime here, including the time for the last, failed VDC allocation
        runtime=float( line.split()[3])
        continue
      else:
        nvms = max(nvms,int(line.split()[0]))
  except Exception as inst:
    print("Error reading " + instance_log)
    print(sys.exc_info()[0])
    break
  
  summary.write("fmcad13_z3_mode" + mode + "\t" + datacenter + "\t" + instance + "\t" + str(nvms) + "\t" + str(runtime) +"\n")
  
  #log all runtimes from runlim, for double-checking purposes
  tmp = open(runlim_tmp)
  log.write(tmp.read())
  log.flush();
  
  tmp.close()
  summary.flush()
summary.close()
log.close()
os.remove(runlim_tmp)
