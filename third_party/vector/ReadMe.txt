--------------------------------------------------------------------------------

                            XL Driver Library

                                   for

                           Windows 10 - 64 Bit
                           Windows 11 - 64 Bit


                      Vector Informatik GmbH, Stuttgart

--------------------------------------------------------------------------------

                      Date          : 09.05.2025
                      DLL Version   :   25.20.14

--------------------------------------------------------------------------------


Vector Informatik GmbH
Ingersheimer Strasse 24
70499 Stuttgart, Germany

Phone: ++49 - 711 - 80670 - 0
Fax:   ++49 - 711 - 80670 - 111


--------------------------------------------------------------------------------

Content
-------
1. Overview
2. Files
3. Installation
4. History

--------------------------------------------------------------------------------

1. Overview:
------------

The XL Driver Library runs only on the following Vector hardware:

- VN0600 Interface Family
- VN1500 Interface Family
- VN1600 Interface Family
- VN2600 Interface Family
- VN5000 Interface Family
- VN7000 Interface Family
- VN8800 Interface Family
- VN8900 Interface Family
- VT6306(B)
- VX0312/VX1135/VX1161.41


2. Files:
---------
 
ReadMe.txt                    This file.


2.1 bin folder:
----------------

bin\vxlapi.dll                XL Driver Library DLL. This file may be present in the folder with your application.
                              If this DLL is not available in your application directory the DLL of
                              the Windows system directory will be used.
                              Note: Vector XL Driver Library Setup installs a copy of this DLL in the Windows 
                                    system directory.

bin\vxlapi.lib                Import library for vxlapi.dll.

bin\vxlapi.h                  Header file for the XL Driver Library.

bin\vxlapi64.dll              64 Bit version of XL Driver Library DLL. Refer to description of vxlapi.dll above.
                              This file may be distributed with your application.

bin\vxlapi64.lib              Import library for vxlapi64.dll.

bin\vxlapi_NET.dll            .NET Wrapper for .NET applications.
                              This file may be distributed with your application.
bin\vxlapi_NET.xml            XML documentation for .NET Wrapper

bin\Vector.XlApi-<version>.nupkg
                              NuGet package for the Vector.XlApi wrapper.
                              The content of this package may be distributed with your application.

bin\netstandard2.0\Vector.XlApi.deps.json
                              Runtime dependency configuration of Vector.XlApi.
                              This file may be distributed with your application.

bin\netstandard2.0\Vector.XlApi.dll
                              Vector.XlApi .NET wrapper library.
                              This file may be distributed with your application.

bin\netstandard2.0\Vector.XlApi.xml
                              XML documentation for Vector.XlApi.
							  

2.2 BuildProperties:
--------------------

BuildProperties\xlapiSamples.props
                              Property file for the sample versions 


2.3 doc folder:
----------------

doc\XL Driver Library - Description.pdf
                              Description for the XL Driver Library function calls.

doc\TC_XLDriverLibrary_VI.pdf     
                              Terms and Conditions for the Use of XL Driver Library.

2.4 exec folder:
----------------

exec\NET\xlA429demo_Csharp.exe
                              C# ARINC application with the vxlapi .NET 3.5 wrapper

exec\NET\xlCANdemo_Csharp.exe
                              C# CAN application with the vxlapi .NET 3.5 wrapper.

exec\NET\xlCANdemo_VBnet.exe
                              Visual Basic .NET advanced CAN example. (vxlapi .NET 3.5 wrapper).

exec\NET\xlCANFDdemo_Csharp.exe
                              C# CAN-FD application with the vxlapi .NET 3.5 wrapper.
                              
exec\NET\xlDAIOexample_Csharp.exe
                              C# Digital-IO application for the vxlapi .NET 3.5 wrapper. 

exec\NET\xlEthernetDemo_Csharp.exe
                              C# channel-based Ethernet application for the vxlapi .NET 3.5 wrapper. 

exec\NET\xlFRdemo_Csharp.exe
                              C# Flexray application for the vxlapi .NET 3.5 wrapper. 
                              
exec\NET\xlIOpiggyExample_Csharp
                              C# DAIO application for the vxlapi .NET 3.5 wrapper.

exec\NET\xlKLineDemo_Csharp.exe
                              C# K-Line application for the vxlapi .NET 3.5 wrapper. 

exec\NET\xlLINdemo_Csharp.exe
                              C# LIN application for the vxlapi .NET 3.5 wrapper. 

exec\NET\xlLINdemo_Single_Csharp.exe
                              C# LIN application with LIN master and slave on same channel for the vxlapi .NET 3.5 wrapper.

exec\NET\xlNetEthDemo_Csharp.exe
                              C# network-based Ethernet application for the Vector.XlApi wrapper and .NET Framework 4.7.2.
							  
exec\NET\xlTimeSyncMonitor_Csharp.exe
							  C# TimeSync demo application for the time synchronization functionality (needs Vector DriverPackage >= V25.20)

exec\Fibex2CSharpReaderDemo.exe
                              C# example how to use the Fibex Reader Demo implementation
							  

exec\xlA429control.exe        32 Bit Visual Studio Project (with MFC) to demonstrate the ARINC functionality.

exec\xlCANcontrol.exe         32 Bit Visual Studio Project (with MFC) to demonstrate the CAN functionality.

exec\xlCANdemo.exe            32 Bit Visual Studio Project (only C) for CAN

exec\xlCANdemo_x64.exe        64 Bit Visual Studio Project (only C) for CAN

exec\xlDAIOdemo.exe           32 Bit Visual Studio Project (with MFC) for digital/analog IO applications.

exec\xlDAIOexample.exe        32 Bit Visual Studio commandline project for digital/analog IO applications.

exec\xlDAIOexample_x64.exe    64 Bit Visual Studio commandline project for digital/analog IO applications.

exec\xlEthBypassDemo.exe      32 Bit Visual Studio Project to demonstrate the channel-based Ethernet bypass functionality. 
 
exec\xlEthDemo.exe            32 Bit Visual Studio Project to demonstrate the channel-based Ethernet functionality. 

exec\xlFlexDemo.exe           32 Bit Visual Studio Project (with MFC) to demonstrate the FlexRay functionality.

exec\xlFlexDemo_x64.exe       64 Bit Visual Studio Project (with MFC) to demonstrate the FlexRay functionality.

exec\xlFlexDemoCmdLine.exe    32 Bit Visual Studio Project to demonstrate the FlexRay functionality.
                             
exec\xlLINExample.exe         32 Bit Visual Studio Project (with MFC) to show the LIN implementation.

exec\xlMostView.exe           32 Bit Visual Studio Project (with MFC) to demonstrate the MOST functionality.

exec\xlMostView64.exe         64 Bit Visual Studio Project (with MFC) to demonstrate the MOST functionality.
                              
exec\xlMost150View.exe        32 Bit Visual Studio Project (with MFC) to demonstrate the MOST150 functionality.

exec\xlMost150View64.exe      64 Bit Visual Studio Project (with MFC) to demonstrate the MOST150 functionality.                              

exec\xlNetEthDemo.exe         32 bit Visual Studio Project to demonstrate network-based Ethernet functionality.

exec\xlVTssDemo.exe           32 bit Visual Studio Project to demonstrate the TimeSync functionality.


2.5 samples folder:
-------------------
samples\NET\xlA429demo_Csharp
samples\NET\xlCANdemo_Csharp
samples\NET\xlCANdemo_VBnet
samples\NET\xlCANFDdemo_Csharp
samples\NET\xlDAIOexample_Csharp
samples\NET\xlEthernetDemo_Csharp
samples\NET\xlFRdemo_Csharp
samples\NET\xlIOpiggyExample_Csharp
samples\NET\xlKlineDemp_Csharp
samples\NET\xlLINdemo_Csharp
samples\NET\xlLINdemo_Single_Csharp
samples\NET\xlNetEthDemo_Csharp
samples\NET\xlTimeSyncMonitor_Csharp
samples\Fibex2CSharpReaderDemo
samples\FibexReaderFlexray
samples\xlA429control
samples\xlCANcontrol
samples\xlCANdemo
samples\xlDAIOdemo
samples\xlDAIOexample
samples\xlEthBypassDemo
samples\xlEthDemo
samples\xlFlexDemo
samples\xlFlexDemoCmdLine
samples\xlKlineDemo
samples\xlLinExample
samples\xlMOSTView
samples\xlMOST150View
samples\xlNetEthDemo
samples\xlVTssDemo

The sample applications are generated with Microsoft VC++ 2017/2022.

3. Installation:
----------------

- Install the latest drivers for your Vector hardware. 

  You can download them under "Support & Downloads" from:

  http://www.vector.com

  The driver setup copies the vxlapi.dll and vxlapi64.dll into your system folders. 


4. History:
-----------
Date:     09.05.2025
Version:       25.20
Note:
- General
  + New API for TimeSync added.
  + Support for new transceiver added:
	- NXP 1462BT (CAN)
	- MaxLinear GPY215 (ETH)
	- Marvell 88Q2221M
	- Broadcom BCM89892
	- Microchip LAN8680
	
- FlexRay
  + xlFrSetMode update (selCycle)
   
- Samples
  + New TimeSync samples added:
    - xlVTssDemo
    - xlTimeSyncMonitor_Csharp (needs Vector DriverPackage >= V25.20)

- Documentation
  + XL Driver Library - Description.pdf - New TimeSync chapter
  + TC_XLDriverLibrary_VI.pdf - "Terms and Conditions for the Use of XL API" added (V1.2)

Date:     12.12.2024
Version:       24.40
Note:
- General
  + Support for new devices:
    - VN5614/VN5611/VN5612/VN5620A 
    - VN1670/VN1641
    - VT6104B/VT6204B
  + Support for new transceiver added: 
    - TLE7259-3GE 
    - TJA 1057B 
    - TLE7259-3GE 
    - BCM89883 
    - 88Q2220M 
    - DAIO 8644
  + New API for more than 64 channels support added
  + Ethernet: VP usage is limited to one per switch

- Samples
  + Refactoring and minor improvements of xlNetEthDemo
  + Refactoring xlDAIOexample
  + Several improvements

- Documentation
  + New API description for more than 64 channels added
  + Device configuration description with VHM updated

Date:     01.02.2021
Version:       20.30
Note:
- General
  + Support for VN5650 and VN5240 added

- Samples
  + New .NET sample for network-based Ethernet

- Documentation
  + Documentation for the new .NET Wrapper added
  + Minor improvements

- .NET Wrapper
  + New .NET Wrapper with support for network-based Ethernet


Date:     04.08.2020
Version:        11.6
Note:
- General
  + Support for Network-based Ethernet access mode (C++)
  + New functions to query driver configuration (C++)
  + Modernized setup

- Samples
  + New C++ sample for network-based Ethernet
  
- Documentation
  + New documentation for network-based ethernet and driver config
  + Several improvements

- .NET Wrapper
  + New defines added
  + A modernized .NET Wrapper with support for Network-based Ethernet
    is scheduled for end of 2020.

Date:     15.03.2019
Version:        11.0
Note:
- General
  + K-Line support (C++ and .NET)
  + Support for new Vector License Model

- DAIO
  + Digital Switch function

- MOST
  + Analysis licence check removed

- Samples
  + new K-Line samples (C++ and .NET)
  + sample solutions now for VS2017

- .NET wrapper
  + K-Line support
  + CAN-FD ISO/ NO-ISO switch
  + several fixes



Date:     06.07.2016
Version:         9.7
Note:
- General
  + ARINC support
  + Keyman support added
  + Documentation update. All bussystems are in one PDF

- A429
  + new ARINC API added.

- CAN
  + new CAN-FD flags (e.g. CAN-FD ISO, CAN-FD BOSCH etc.).
    
- Samples
  + new A429 samples (C++ and .NET)
  + sample solutions now for VS2013
  + xlFlexDemo: Keyman support added
  
- .NET wrapper
  + vxlapi.dll adaption modified
  + ARINC support
  + Keyman support
  


Date:     06.11.2014
Version:         9.0
Note:
- General
  + all Documentation update

- Ethernet
  + new API added.

- CAN
  + CAN-FD support added. (new API functions)
  
- DAIO
  + VN89xx support
  
- Samples
  + xlCANdemo: CAN-FD support added
  + xlDAIOexample: support for all DAIO types
  + xlEthDemo: new example
  + xlEthBypassDemo: new example
  
- .NET wrapper
  + new examples (old ones are removed)
  + CAN-FD support
  + Ethernet support
  + DAIO (VN89xx/VN16xx) piggy support
  + DAIO example added
  + ComfortLayer removed 

  
  
Date:     11.01.2013
Version:         8.3
Note:
- General
  + VN7570 / VN5610 (CAN only) support
  + Support for new Piggy types
  + Added XL_EVENT_FLAG_OVERRUN handling
  + Added function xlGetChannelTime
 
- MOST
  + Added missing event source mask bits (AllocTabel + SyncStreaming)
  + Added support for mostSyncTxUnderflow and mostSyncRxOverflow events

- Flexray
  + Added Flexray Acceptance Filter (xlFrSetAcceptanceFilter) to advanced version of XLAPI Library

- DAIO
  + Added support for VN16xx IO-Feature
  
- Samples
  + Support for Visual Studio 2008
  + xlFlexDemo updated
  + xlCANControl updated
  + Flexray FibexReader updated
  + xlCANdemo_NET20_C#_Advanced updated

- .NET wrapper
  + ComfortLayer: Increased RX-Queue size for CAN to 256 events
  + Added XL_APPLICATION_NOTIFICATION event



Date:     14.12.2011
Version:         8.0
Note:
- General
  + Release of MOST150 API functionality
  + 'XL Driver Library - MOST150 Description.pdf' added.
  + VN8900 support - xlGetRemoveDriverConfig() added
 
- Samples
  + xlMOST150View sample added
  + xlMOSTView update 
  + xlFlexDemo update
  + xlCANDemo update
  + xlCANControl update

- .NET wrapper
  + channelIdx in driverConfig structure
  + xlSetGlobalTimeSync function added
  + xlFRactiveSpy added
  + xlGetRemoteDriverConfig added
  + xlReceive multiple events can be received
 


Date:     08.09.2010
Version:         7.5
Note:
- General
  + Added missing Vector hardware type defines to .NET wrapper
  + Fixed issue in .NET-Wrapper Comfort Layer when opening/closing multiple channels multiple times

- LIN, IO-Cab
  + Fixed bit corruption of 2nd data byte in rx-events



Date:     27.07.2010
Version:         7.4
Note:
- General
  + New API function xlGetLicenseInfo for requesting the currently present licences on Vector devices
  + New API function xlSetTimerRateAndChannel for setting fast timerrates
  + New API function xlSetTimerBasedNotify for notification of application at cyclic time values
  + Added 64bit support for native applications and .NET applications
  + Re-added define 'XL_HWTYPE_CANAC2PCI' for compatibility reasons

- LIN
  + Added new define for LIN 2.1
  + Added .NET demo for LIN master and slave on the same channel

- CAN
  + 64 Bit example application
  
- Flexray
  + New commandline based demo application
  + Example application for reading Fibex files
  + 64 Bit example application

- MOST
  + Fixed defines XL_MOST_LIGHT_* to be used in xlMostSetTxLightPower API function
  + Added flag for detecting MOST queue-overflows in driver (XL_MOST_QUEUE_OVERFLOW_DRV)
  + Increased max. allowed RX-FIFO size to 1MB



Date:     27.08.2008
Version:         6.7
Note:
- FlexRay: 
  + Mulitapplication support added (needs FR driver >= 6.7)
  + Spy mode added
  + 'XL Driver Library - FlexRay Description.pdf' update
  + xlFlexDemo update
- MOST: 
  + New feature streaming added. (needs MOST driver >= 6.4)
  + 'XL Driver Library - MOST Description.pdf' update
  + xlMOSTView update
  
  

Date:     21.06.2007
Version:         6.4
Note:
- FlexRay: new bussytem added (needs VN3x00 driver > V6.4)
  + 'XL Driver Library - Description.pdf' updated.
  + 'XL Driver Library - FlexRay Description.pdf' added.
- LIN: faster function calls:
  + xlActivateChannel for LIN
  + xlLinSetSlave
- MOST: fixed xlMostSyncAudio/Ex for Free library.
- .NET wrapper update:
  + examples update
  + new DAIO example



Date:     21.06.2006
Version:         5.7
Note:
- MOST: SPDIF support for VN2610 added: 
  + new function xlMostCtrlSyncAudioEx
  + new event XL_MOST_CTRL_SYNC_AUDIO_EX
  + new event XL_MOST_TIMINGMODE_SPDIF
- .NET wrapper: update to .NET Framework 1.1 and 2.0
  + 'XL Driver Library - .NET Wrapper Description.pdf' added.
  + new C# LIN example
- LIN: xlLinSwitchSlave update:
  + defines updated
  + now possible on a LIN master including a slave. 
- CAN: xlCanSetChannelOutput modified: 
  + XL_OUTPUT_MODE_SILENT flag modified. 
- VB examples: xlVBCANapp modified.
- 'XL Driver Library - Description.pdf' updated.
        
        
        
Date:     21.11.2005
Version:         5.5
Note:
- LIN: new function xlLinSwitchSlave to switch on/off a LIN slave.
- CAN: fix for multiapplication.



Date:     31.08.2005
Version:         5.4
Note:
- MOST: new MOST API (Free- and 'Most Analysis' library) added. 
  + 'XL Driver Library - Description.pdf' updated.
  + 'XL Driver Library - MOST Description.pdf' added.
- .NET wrapper and examples added:
  + xlCANdemo_NET_Csharp_Advanced 
  + xlCANdemo_NET_Csharp_Easy     
  + xlCANdemo_NET_Delphi_Advanced 
  + xlCANdemo_NET_Delphi_Easy     
  + xlCANdemo_NET_VBnet_Advanced  
  + xlCANdemo_NET_VBnet_Easy       
- XLAPI supports now Dev-C++ (MinGW). The xlCANdemo 
  includes a project file.
  + xlCANdemo.dev added.
  + xlCANdemoDL.dev added.
- VB examples: Declarations.vb updated.    



Date:     13.04.2005
Version:         5.3
Note:   
- new Visual Basic .NET example for LIN included.  
- LIN: LIN 2.0 support in xlLinSetChannelParams.
- LIN: new function xlLINSetChecksum and CRC info event added.
- LIN: fix in xlLinSetDLC.
- LIN: better error handling in xlLinSetSlave.
- CAN: xlCanSetChannelOutput with new flag XL_OUTPUT_MODE_TX_OFF.
  (also updated in xlCANdemo).
- workaround for BCB 6 and one-byte alignement.
- updated macro XL_CHANNEL_MASK(x) for 64 channels.  



Date:     24.05.2004
Version:         5.1
Note:   
- new Visual Basic .NET example included.    
- LIN: possible slave task within a master node. 
- LIN: faster execution time in xlLinSetSlave.
- CAN: fixed xlCanSetChannelTransceiver function.
- fixed critical sections.
- documentation update.



Date:     02.04.2004
Version:        5.00
Note:     First Release		







