add_lldb_library(lldbPluginObjectFileWasm PLUGIN
  ObjectFileWasm.cpp

  LINK_COMPONENTS
    Object
    Support
  LINK_LIBS
    lldbCore
    lldbHost
    lldbSymbol
    lldbUtility
  )
