import json
import networkx as nx
import pulp 
import csv
import time

def CutPartition(remainingGraph, targetPop, popDeviation, populations):
    prog = pulp.LpProblem("CutPartition", pulp.LpMinimize)

    startTime = time.time()
    # Defining Partition Binary
    xVars = []
    xVarMap = {}
    for n in remainingGraph.nodes:
        var = pulp.LpVariable("x" + str(n), cat=pulp.LpBinary)
        xVarMap[n] = var
        xVars.append(var)
        prog += var
    # Defining crossing binary
    edgeVars = []
    weights = []
    for n, m in remainingGraph.edges:
        edgeVal = pulp.LpAffineExpression([(xVarMap[n], 1), (xVarMap[m], -1)])
        absEdgeVal = pulp.LpVariable('y' + str(n) + str(m), cat=pulp.LpBinary)

        # Tries to fix absolute value prob
        prog += absEdgeVal >= edgeVal
        prog += absEdgeVal >= -edgeVal

        edgeVars.append(absEdgeVal)
        weights.append(remainingGraph[n][m]['weight'])
    # Subset sum
    popVariables = []
    for i in range(len(xVars)):
        popVariables.append(pulp.LpAffineExpression(xVars[i] * populations[i]))
    # Max Pop
    prog += pulp.lpSum(popVariables) <= targetPop * (1 + popDeviation)
    # Min Pop
    prog += pulp.lpSum(popVariables) >= targetPop * (1 - popDeviation)

    # Source Partition Connected
    for i in range(len(xVars)):
        sumParts = []
        for j in range(len(xVars)):
            if i == j: break
            if remainingGraph.has_edge(i, j):
                sumParts.append(remainingGraph[i][j]['weight'] * xVars[j])
        totalLH = pulp.LpAffineExpression(xVars[i] * pulp.lpSum(sumParts))
        prog += pulp.LpConstraint(totalLH, pulp.LpConstraintGE, 0)
    # Define Minimization Target
    # Edgeweights
    edgeWeightVars = []
    for i in range(len(edgeVars)):
        edgeWeightVars.append(pulp.LpAffineExpression(edgeVars[i] * weights[i]))
    prog += pulp.LpAffineExpression(pulp.lpSum(edgeWeightVars), name="Z")

    print("Sending to solver...")
    Solver_name = 'PULP_CBC_CMD'
    solver = pulp.getSolver(Solver_name, threads=4)
    prog.solve(solver)

    toReturn = {}

    districtPop = 0
    for i in range(len(xVars)):
        if(xVars[i].value() == 1):
            districtPop += populations[i]
            toReturn[xVars[i].name] = xVars[i].value()
            print(xVars[i].name, xVars[i].value())
    if(districtPop >= targetPop * (1 + popDeviation) or districtPop <= targetPop * (1-popDeviation)):
        raise ValueError("District Generated not of Proper Population") 
    return toReturn, time.time()-startTime

def processState(stateName):
    dataFile = open("map_data/" + stateName + ".json")
    data = json.load(dataFile)

    adjacencies = []
    countyNames = []
    pop = []
    weights = []
    for countyInfo in data:
        countyNames.append(countyInfo["GEOID"])
        adjacencies.append(countyInfo["adj"])
        pop.append(countyInfo["pop"])
        weights.append(countyInfo["weights"])

    # Population Tolerance
    ALPHA = .05

    stateGraph = nx.Graph()

    totalPop = 0
    # Add the nodes as necessary
    for i in range(len(adjacencies)):
        # Adds node for each set of adjacencies
        totalPop += pop[i]
        # Adds necessary edges; double-adding doesn't matter
        # try:
        for j in range(len(adjacencies[i])):
            # print(i,j)
            stateGraph.add_edge(countyNames[i], countyNames[adjacencies[i][j]], weight=float(weights[i][j]))
        # except:
        #         print(i)
        #         stateGraph.add_edge(countyNames[i], countyNames[adjacencies[i]], weight=weights[i])

    # Population per district
    # TODO: FIX:
    numDistricts = 4
    targetPop = totalPop / numDistricts
    remainingGraph = stateGraph.copy()
    districts = []
    runTimes = []
    while len(districts) < numDistricts - 1:
        cutResult, runtime = CutPartition(remainingGraph, targetPop, ALPHA, pop)
        runTimes.append(runtime)
        newDistrict = []
        for d in cutResult.keys():
            # Gets rid of the x
            # print(d)
            newDistrict.append(d[1:])
        # Appends the new district to our list of districts
        districts.append(newDistrict)
        oldSize = remainingGraph.order()
        # Removes those nodes from the district
        remainingGraph.remove_nodes_from(newDistrict)
        newSize = remainingGraph.order()
        # Verify that all of the nodes were removed
        if(newSize != oldSize - len(newDistrict)):
            print(remainingGraph.nodes)
            print(newDistrict)
            raise(ValueError("Districts were not removed appropriately"))
        # print(newDistrict)
    newDistrict = []
    for d in remainingGraph.nodes:
        # Gets rid of the x
        newDistrict.append(d)
    districts.append(newDistrict)

    #Confirm total size is appropriate
    totalCountiesinDistricts = 0
    for d in districts:
        totalCountiesinDistricts += len(d)
    if(totalCountiesinDistricts != len(countyNames)):
        raise(ValueError("Number of districts in plan does not match number of districts."))

    districtFile = open("district_outputs/" + stateName + '.csv', 'w+')
    districtWriter = csv.writer(districtFile)
    districtWriter.writerow(["district", "precinct"])
    for i in range(len(districts)):
        for j in range(len(districts[i])):
            districtWriter.writerow([i + 1, districts[i][j]])
    districtFile.close()

    timeFile = open("runtimes/" + stateName + '.csv', 'w+')
    timeWriter = csv.writer(timeFile)
    timeWriter.writerow(["district", "runtime"])
    for i in range(len(runTimes)):
        timeWriter.writerow([i, runTimes[i]])
    timeWriter.writerow(['Sum:', sum(runTimes)])
    timeFile.close()



