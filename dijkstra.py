# !/usr/bin/python

#+ + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + +
#+ RUN THE CODE USING THIS COMMAND                             +
#+ python dijkstra.py --rid routerID                           +
#+                                                             +
#+ copyright Oluwamayowa Adeleke                               +
#+ free to use, and distribute, edit and redistribute as you   +
#+ desire, just add the line below to the your code            +
#+ "#parts of code written by Oluwamayowa Adeleke"             +
#+ + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + +

import sys
import IPy
import json
import time
import socket
import datetime
import netifaces
import threading
import networkx
from pyroute2 import IPRoute

MY_LOCK = threading.Lock()

class myThread (threading.Thread):
  noOfThreads=0
  threadlist = []
  def __init__(self, targetMethod, name=None, arg1=None ):
    print "16 - entering new thread __init__ "
    threading.Thread.__init__(self,target=targetMethod, args=(arg1,))
    myThread.noOfThreads+=1
    self.threadID = myThread.noOfThreads
    self.name = name
    self.stopThread=False
    myThread.threadlist.append(self)
    print "17 - exiting new thread __init__ "


def getLocalNetworksDetails():
  print "2 - getting local network details"
  localNetworksDetails = {}
  interfacesList = netifaces.interfaces()
  print "3 - entering for loop"
  for interface in interfacesList:
    print "4 - a for loop iteration"
    layer3addresses = []
    try:
      print "5 - in Try block"
      print ""
      layer3addresses = netifaces.ifaddresses(interface)[netifaces.AF_INET]
    except Exception:
      print "6 - in except block"
      pass
    print "7 - entering for loop"
    for ipAddr in layer3addresses:
      print "8 - a for loop iteration"
      ipCIDR=ipAddr['addr'] + "/" + ipAddr['netmask']
      networkAddr = IPy.IP(ipCIDR, make_net=True).strNormal()
      #TODO find a way to pull the interface bandwidth here
      bandwidth = 1000
      localNetworksDetails[networkAddr]={'interface':interface, "bandwidth":bandwidth, "ipCIDR":ipCIDR}
  print "9 - exiting getLocalNetwork details"
  return localNetworksDetails

def HelloSenderManager(arg1={}):
  print "20 - entering hello sender manager "
  helloSendInterval = arg1['helloSendInterval']
  helloServerPort = arg1['helloServerPort']
  currThread = threading.currentThread()
  "20 - entering s"
  while currThread.stopThread == False:
    helloPacketData = createMyHelloPacket()
    sendMyHelloPacket(helloPacketData,helloServerPort)
    time.sleep(helloSendInterval)

def createMyHelloPacket():
  global mygraph
  global thisRouterID
  MY_LOCK.acquire()
  #TODO: ?? do i need to put the below read in a lock?
  graphDictString = json.dumps(mygraph.to_dict_of_dicts())
  #my_dict = json.loads(graphDictString)
  MY_LOCK.release()
  packetdata = thisRouterID + " " + graphDictString
  return packetdata

def sendMyHelloPacket(helloPacketData, helloServerPort):
  #send this packet to my local network broadcasts.
  global localNetworksDetails
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
  # TODO: ?? do i need to put the below read in a lock?
  for networkAddress, details in localNetworksDetails.iteritems:
    broadcastAddr = IPy.IP(networkAddress).broadcast().strNormal()
    sock.sendto(helloPacketData, (broadcastAddr, helloServerPort))
  sock.close()

def helloListenerManager(arg1={}):
  host = '0.0.0.0'
  helloServerPort = arg1['helloServerPort']
  helloServerBufferSize = arg1['helloServerBufferSize']
  helloServerSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  helloServerSocket.bind((host, helloServerPort))
  helloServerSubThreads = []

  currThread = threading.currentThread()
  while currThread.stopThread == False:
    print "[hello] Listener Server is listening"
    (data, (ip, port)) = helloServerSocket.recvfrom(helloServerBufferSize)
    print "[hello] new message from [", ip, ":", port, "]"
    newHelloListenerThread = threading.Thread(target=handleHelloMsgRxd, args=(data, ip, port))
    newHelloListenerThread.start()
    helloServerSubThreads.append(newHelloListenerThread)

  for helloServerSubThread in helloServerSubThreads:
    helloServerSubThread.join()

def handleHelloMsgRxd(data, ip, port):
  global mygraph
  global thisRouterID
  global localNetworksDetails
  global neighbourIplist

  #print "[Hello] message received from ["+str(ip)+":"+str(port)+ "] :::: data ---> ", data
  dataArray = data.split('',1)

  neighbourRouterID = dataArray[0]
  dataGraphDict = json.loads(dataArray[1])
  rxDataGraph = networkx.Graph(dataGraphDict)

  MY_LOCK.acquire()

  if ip not in neighbourIplist:
    neighbourIplist.append(ip)

  tempgraph = mygraph.copy()
  #add neighbor node
  if tempgraph.has_node(neighbourRouterID) == False:
    tempgraph.add_node(neighbourRouterID)
    tempgraph.node[neighbourRouterID]['RouterID'] = neighbourRouterID
    tempgraph.node[neighbourRouterID]['networks'] = rxDataGraph.node[neighbourRouterID]['networks']
  # add edge to neighbor
  for netAddr, details in tempgraph.node[neighbourRouterID]['networks']:
    if IPy.IP(ip) in IPy.IP(netAddr, make_net=True):
      if tempgraph.has_edge(thisRouterID, neighbourRouterID, networkAddr=netAddr) == False:
        #TODO get bandwidth and delay then calculate weight and add as attribute in add_edge below, a
        #bandwidth = min(bandwidth from myself, bandwidth from neighbor)
        #delay = delay from myself interface + delay from neighbours interface
        tempgraph.add_edge(thisRouterID, neighbourRouterID, networkAddr=netAddr, weight=1)

  #now merge temp-own graph and neighbour graph
  tempgraph = networkx.algorithms.compose(tempgraph, rxDataGraph)

  #if there is difference between old and new Graphs call the recalculate routes function
  graphIsSame = networkx.algorithms.isomorphism.is_isomorphic( mygraph, tempgraph, node_match=compareNodes, edge_match=compareEdges)
  if graphIsSame == False:
    mygraph = tempgraph.copy()
  MY_LOCK.release()
  if graphIsSame == False:
    calculateBestRoutes(tempgraph)



def compareNodes(nodeInG1, nodeInG2):
  if nodeInG1['routerID'] == nodeInG2['routerID']:
    networkIsMatched=True
    for netAddr, details in  nodeInG1['networks']:
      if nodeInG1['networks'][netAddr] and nodeInG2['networks'][netAddr] and nodeInG1['networks'][netAddr]== nodeInG2['networks'][netAddr]:
        pass
      else:
        networkIsMatched = False
    return networkIsMatched
  return False


def compareEdges(edge1, edge2):
  if edge1['networkAddr'] == edge2['networkAddr'] and edge1['weight'] == edge2['weight']:
    #TODO add checks for bandwidth and delay in the above if statement
    return True
  return False


def calculateBestRoutes(topoGraph):
  global thisRouterID
  global neighbourIplist

  #first make network - routers list
  network_router_List = {}
  for nodei in topoGraph.nodes(data=True):
    for networki in nodei['networks'].keys():
      if networki not in network_router_List.keys():
          network_router_List[networki]=[]
      if nodei['routerID'] not in network_router_List[networki]:
          network_router_List[networki].append(nodei['routerID'])

  #calculate best path to all routers using dijkstra  -- returns a dictionary
  #TODO implement my own Dijkstra
  MY_LOCK.acquire()
  lengthToRouterDict, pathToRouterDict = networkx.single_source_dijkstra(topoGraph, thisRouterID)
  MY_LOCK.release()

  #determine exit interfaces for each network from length and path above
  network_exit_int_nexthop_Dict = {}
  for net, routers in network_router_List.iteritems():
    bestRouter = ""
    bestLength = sys.maxint
    bestPath = None
    for router in routers:
      if lengthToRouterDict[router] < bestLength:
        bestLength = lengthToRouterDict[router]
        bestRouter = router
        bestPath = pathToRouterDict[router]
    nexthop = bestPath[1] #a router id

    #TODO dont know how this below will respond for multilinks between same nodes...
    #TODO ...can find a way to get key of the link with lowest weight and add that below.
    networkToNextHop = topoGraph[thisRouterID][nexthop]["networkAddr"]


    exitInterface=topoGraph[thisRouterID]['networks'][networkToNextHop]["interface"]

    #TODO if we need next hop IP instead, we can push that into a list from within...
    #TODO ...function handleHelloMsgRxd(data, ip, port): and use it here.
    MY_LOCK.acquire()
    nexthopIp = None
    for neighborIp in neighbourIplist:
      if neighborIp in IPy.IP(networkToNextHop):
        nexthopIp = neighborIp
        break
    MY_LOCK.release()
    network_exit_int_nexthop_Dict[net] = (exitInterface, nexthopIp)


  updateLinuxRouteTable(network_exit_int_nexthop_Dict,)

def updateLinuxRouteTable(network_exit_int_nexthop_Dict):
  #TODO write code to update the linux routing table
  for net, int_exitInterface_tuple in network_exit_int_nexthop_Dict.iteritems():
    currentRoute = (IPRoute().route('get', dst=IPy.IP(net)[1].strNormal()))
    currentNextHop = currentRoute[0]['attrs'][4][1]
    if currentNextHop != int_exitInterface_tuple[1]:
      netarray = net.split('/')
      IPRoute().route("add", dst=netarray[0], mask=netarray[0], gateway=int_exitInterface_tuple[1])
      #TODO pull the values of dst and mask from an IP(net)objet instead

      # TODO remove direct networks from this update.
  pass




# BEGIN EXECUTION HERE
argList = str(sys.argv)
thisRouterID = argList[len(argList) - 1]
#TODO make the above line detect router ID with unordered arguments.

# GLOBAL VARIABLES
#networksList = [] #list of neighbourObjects
#routersList = [] #list of routerObjects
#TODO is it better to use a dict for the above 2 variables instead of a list?
localNetworksDetails = {} #list of string NetAddrs to track my local Nets
neighbourIplist = [] #dict of string IPs to track my neighbours.

#CONFIG VARIABLES
config={}
config['helloSendInterval']=5 #in secs
config['helloServerPort']=19190
config['helloServerBufferSize']=1204


#PHASE 1 - INITIALIZE MYSELF
print "1 - PHASE 1 starts"
#TODO maybe I really dont need a router object and network object, the Graph covers all.
localNetworksDetails = getLocalNetworksDetails()   #from Configured IP addresses
print "10 - PHASE 1 ends"

#PHASE 2 CREATE TOPOLOGY GRAPH OF ROUTERS AS NODES
print "11 - PHASE 2 starts"
mygraph = networkx.MultiGraph()
mygraph.add_node(thisRouterID)
mygraph.node[thisRouterID]['RouterID'] = thisRouterID
mygraph.node[thisRouterID]['networks'] = localNetworksDetails
print "12 - PHASE 2 ends"

#PHASE 3: SEND OUT HELLO PACKET CONTAINING GRAPH TOPOLOGY
#this must be done in a seprate thread
print "13 - PHASE 3 starts"
arg1={'helloSendInterval':config['helloSendInterval'], 'helloSendPort':config['helloServerPort']}
print "14 - creating hello sender thread object"
helloSenderThread = myThread(HelloSenderManager, "helloSenderThread", arg1)
print "18 - starting hello sender thread"
helloSenderThread.start()
print " - PHASE 3 ends"

#PHASE 4: FOR RX NEIGHBOUR PACKETS
#this must be done in a seprate thread
print " - PHASE 4 starts"
arg1={'helloSendPort':config['helloServerPort'], 'helloServerBufferSize':config['helloServerBufferSize']}
print " - creating hello listener thread object"
helloListenerThread = myThread(helloListenerManager, "helloListenerThread", arg1)
print " - starting hello listener thread"
helloListenerThread.start()


#PHASE 4: ROUTES CALCULATION.
#the calculateBestRoutes(graph) method is called from the handleHelloMsgRxd()
#done


#PHASE 5
#the updateLinuxRouteTable(network_exit_intfaceList) method is called from the calculateBestRoutes()
#done

#PHASE 6
'''
routerdeadmonitor
If nothing receieved for a neighbour in 5 ses
	Create deadnoticepacket broadcast out
	Keep a list. Of deadnotify sent
	remove neighbour router. And routes through it
	Call recalculate routes
'''


#PHASE 7
'''
On receive a dead notify packet
	Chek if already received in last 10 secs
		If yes: don’t forward packet.
		If no: forward out all ports (except the one where it was received?)
	remove neighbour router.  And routes through it.
Call recalculate routes.
'''




