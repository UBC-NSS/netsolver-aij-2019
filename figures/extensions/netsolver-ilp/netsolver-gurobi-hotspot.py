#!/usr/bin/python3

import argparse
import datetime
import json
import statistics
import time
from gurobipy import *

trueList = ['true', 't', '1']

parser = argparse.ArgumentParser()
parser.add_argument("PhysicalNetwork", help="Path to the physical network file", type=str)
parser.add_argument("VirtualNetwork", help="Path to the virtual network file", type=str)
parser.add_argument("IsUndirected", help="Flag to indicate whether physical network is undirected or not")
parser.add_argument("IsMultiThreaded", help="Flag to indicate whether Gurobi ILP solver can spawn multiple threads for solving")
parser.add_argument("OutputFile", help="File to stream timestamp output to after each allocation is made",type=str)
args = parser.parse_args()

# Physical/virtual network file loading (custom simple files here for now)
start = datetime.datetime.now()
pn = json.load(open(args.PhysicalNetwork))
vn = json.load(open(args.VirtualNetwork))
out = open(args.OutputFile, "w")
isUndirected = args.IsUndirected.lower() in trueList
isMultiThreaded = args.IsMultiThreaded.lower() in trueList

virtualPhysicalServerPairs = tuplelist([(i, j) for i in vn["VMs"].keys() for j in pn["Servers"].keys()])

# Build the virtual server requirements here
virtualServerCpuRequirements = tupledict()
virtualServerRamRequirements = tupledict()
virtualServerThirdRequirements = tupledict()

for i in vn["VMs"].keys():
    for j in virtualPhysicalServerPairs.select(i, '*'):
        virtualServerCpuRequirements[j] = vn["VMs"][i][0]
        virtualServerRamRequirements[j] = vn["VMs"][i][1]
        virtualServerThirdRequirements[j] = vn["VMs"][i][2]

# Build commodities (virtual source-destination pair tuples) and bandwidth requirements here
commodities = tuplelist()
bandwidthReqs = tupledict()
for i in vn["VN"]:
    commodities.append((i[0], i[1]))
    bandwidthReqs[(i[0], i[1])] = i[2]

m = Model('netsolver-gurobi')
m.Params.OutputFlag = 0
if isMultiThreaded:
    m.Params.Threads = 0
else:
    m.Params.Threads = 1
place = m.addVars(virtualPhysicalServerPairs, name="place", vtype=GRB.BINARY)
coresUsed = m.addVars(pn["Servers"].keys(), name="coresUsed", vtype=GRB.INTEGER, lb=0)

# Add constraints to ensure that each virtual machine is mapped to a single physical server
equal = m.addConstrs((place.sum(i, '*') == 1 for i in vn["VMs"].keys()), "equal")

# Add constraints to ensure that virtual machine requirements are met by mappings to physical servers
physicalServerResources = [{}, {}, {}]
cpuConstrs = dict()
ramConstrs = dict()
thirdReqConstrs = dict()
coresUsedConstrs = {}
oldCoresUsed = {}
for i in pn["Servers"].keys():
    physicalServerResources[0][i] = pn["Servers"][i][0]
    physicalServerResources[1][i] = pn["Servers"][i][1]
    physicalServerResources[2][i] = pn["Servers"][i][2]
    oldCoresUsed[i] = 0
    cpuConstrs[i] = m.addConstr(virtualServerCpuRequirements.prod(place, '*', i) <= physicalServerResources[0][i], i + "-CpuConstraint")
    ramConstrs[i] = m.addConstr(virtualServerRamRequirements.prod(place, '*', i) <= physicalServerResources[1][i], i + "-RamConstraint")
    thirdReqConstrs[i] = m.addConstr(virtualServerThirdRequirements.prod(place, '*', i) <= physicalServerResources[2][i], i + "-ThirdReqConstraint")
    coresUsedConstrs[i] = m.addConstr(coresUsed[i] - virtualServerCpuRequirements.prod(place, '*', i) >= oldCoresUsed[i], i + "-CoresUsedConstraint")

obj = m.addVar(lb=0.0, obj=1.0, vtype=GRB.INTEGER, name="obj")
m.addConstr(obj == max_(coresUsed))

# Build physical network from JSON input file
# arcs, capacity, cost, nodes variables from Gurobi netflow.py example
arcs = tuplelist()
indexArcs = tuplelist()
capacity = tupledict()
nodes = set()

if isUndirected:
    for i in pn["PN"]:
        arcs.append((i[0], i[1]))
        arcs.append((i[1], i[0]))
        indexArcs.append((i[0], i[1]))
        capacity[(i[0], i[1])] = i[2]
        nodes.add(i[0])
        nodes.add(i[1])

else:
    for i in pn["PN"]:
        arcs.append((i[0], i[1]))
        capacity[(i[0], i[1])] = i[2]
        nodes.add(i[0])
        nodes.add(i[1])

nodes = list(nodes)

# Create inflow dictionary for each source-dest pair (each commodity) here
# - means more inflow than outflow (sink), + means more outflow than inflow (source)
inflow = tupledict()
for i in commodities:
    for j in nodes:
        if j not in pn["Servers"].keys():   # If j is a switch
            inflow[(i, j)] = 0
        else:
            inflow[(i, j)] = (bandwidthReqs[i] * place[(i[0], j)]) - (bandwidthReqs[i] * place[(i[1], j)])

flow = m.addVars(commodities, arcs, name="flow", vtype=GRB.INTEGER, lb=0)

if isUndirected:
    cap = m.addConstrs((flow.sum('*', '*', i, j) + flow.sum('*', '*', j, i) <= capacity[i, j] for i, j in indexArcs), "cap")

else:
    cap = m.addConstrs((flow.sum('*', '*', i, j) <= capacity[i, j] for i, j in arcs), "cap")

node = m.addConstrs((flow.sum(i[0], i[1], '*', j) + inflow[(i, j)] == flow.sum(i[0], i[1], j, '*') for i in commodities for j in nodes), "node")

#m.write("file.lp")

# Compute solution
counter = 0
allocationTimes = []

init = datetime.datetime.now()
delta = init - start
print("# instance {}".format(args.PhysicalNetwork), file=out)
print("# Settings: PN={}, VN={}, multi-thread={}".format(args.PhysicalNetwork, args.VirtualNetwork, isMultiThreaded), file=out)
print("init {} {}".format(delta.total_seconds(), delta.total_seconds()), file=out, flush=True)

m.optimize()

#m.computeIIS()
#m.write("model.ilp")

# Solve repeatedly
while m.status == GRB.Status.OPTIMAL:
    currEnd = datetime.datetime.now()
    allocationTimes.append((currEnd - init).total_seconds())
    counter = counter + 1
    #print('Allocation %g\n' % (counter))
    print("{} {} {}".format(counter, (currEnd - init).total_seconds(), (currEnd - start).total_seconds()), file=out, flush=True)
    
    init = datetime.datetime.now()
    #print('%g seconds since script started\n' % (init - start))
    placeSolution = m.getAttr('x', place)
    flowSolution = m.getAttr('x', flow)
    
    for i in vn["VMs"].keys():
        for j in pn["Servers"].keys():
            if placeSolution[i, j] == 1:
                #print('%s -> %s\n' % (i, j))
                physicalServerResources[0][j] = physicalServerResources[0][j] - virtualServerCpuRequirements[i, j]
                physicalServerResources[1][j] = physicalServerResources[1][j] - virtualServerRamRequirements[i, j]
                physicalServerResources[2][j] = physicalServerResources[2][j] - virtualServerThirdRequirements[i, j]
                oldCoresUsed[j] = oldCoresUsed[j] + virtualServerCpuRequirements[i, j]
                break

    for i in pn["Servers"].keys():
        coresUsedConstrs[i].setAttr(GRB.Attr.RHS, oldCoresUsed[i])
    
    for i in pn["Servers"].keys():
        cpuConstrs[i].setAttr(GRB.Attr.RHS, physicalServerResources[0][i])
        ramConstrs[i].setAttr(GRB.Attr.RHS, physicalServerResources[1][i])
        thirdReqConstrs[i].setAttr(GRB.Attr.RHS, physicalServerResources[2][i])

    if isUndirected:
        for i in commodities:
            #print('For [%s, %s]:\n' % (i[0], i[1]))
            for j, k in indexArcs:
                capacity[j, k] = capacity[j, k] - flowSolution[i[0], i[1], j, k] - flowSolution[i[0], i[1], k, j]
                #print('%s -> %s    -    %g\n' % (j, k, flowSolution[i[0], i[1], j, k]))
                #print('%s -> $s    -    %g\n' % (k, j, flowSolution[i[0], i[1], k, j]))

        for i, j in indexArcs:
            cap[i, j].setAttr(GRB.Attr.RHS, capacity[i, j])

    else:
        for i in commodities:
            for j, k in arcs:
                capacity[j, k] = capacity[j, k] - flowSolution[i[0], i[1], j, k]
                #print('%s -> %s    -    %g\n' % (j, k, flowSolution[i[0], i[1], j, k]))

        for i, j in arcs:
            cap[i, j].setAttr(GRB.Attr.RHS, capacity[i, j])
    
    m.reset()
    m.optimize()
    sys.stdout.flush()

end = datetime.datetime.now()
print("done {} {} {}".format(counter, (end - init).total_seconds(), (end - start).total_seconds()), file=out, flush=True)
print((end - start).total_seconds())
print(counter)
print('Median time: %g s' % (statistics.median(allocationTimes)))
