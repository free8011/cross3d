##
#	\namespace	blur3d.api.abstract.studiomaxapplication
#
#	\remarks	The StudiomaxApplication class will define all operations for application interaction. It is a singleton class, so calling blur3d.api.Application() will
#				always return the same instance of Application. One of its main functions is connecting application callbacks to blur3d.api.Dispatch.
#				
#				The StudiomaxApplication is a QObject instance and any changes to the scene data can be controlled by connecting to the signals defined here.
#
#				When subclassing the AbstractScene, methods tagged as @abstractmethod will be required to be overwritten.  Methods tagged with [virtual]
#				are flagged such that additional operations could be required based on the needs of the method.  All @abstractmethod methods MUST be implemented
#				in a subclass.
#	
#	\author		Mikeh@blur.com
#	\author		Blur Studio
#	\date		06/07/11
#

from blur3d.api.abstract.abstractapplication import AbstractApplication
from Py3dsMax import mxs
from blurdev import debug, enum
dispatch = None

# initialize callback scripts
_STUDIOMAX_CALLBACK_TEMPLATE = """
global blur3d
if ( blur3d == undefined ) then ( blur3d = python.import "blur3d" )
if ( blur3d != undefined ) then ( 
	local ms_args = (callbacks.notificationParam())
	blur3d.api.dispatch.%(function)s "%(signal)s" %(args)s 
)
"""
_STUDIOMAX_CALLBACK_TEMPLATE_NO_ARGS = """
global blur3d
print "Calling maxscript no args %(function)s, |%(signal)s|"
if ( blur3d == undefined ) then ( blur3d = python.import "blur3d" )
if ( blur3d != undefined ) then ( 
	blur3d.api.dispatch.%(function)s "%(signal)s"
)
"""
_STUDIOMAX_VIEWPORT_TEMPLATE = """
fn blurfn_%(signal)s = 
(
	if ( blur3d == undefined ) then ( blur3d = python.import "blur3d" )
	if ( blur3d != undefined ) then ( 
		blur3d.api.dispatch.%(function)s "%(signal)s"
	)
)
"""

class _ConnectionDef:
	ConnectionType = enum.enum('General', 'Viewport')
	def __init__(self, signal, callback, arguments='', function='dispatch', callbackType=ConnectionType.General):
		self.signal = signal
		self.callback = callback
		self.arguments = arguments
		self.function = function
		self.callbackType = callbackType

	@staticmethod
	def asDict(signal, callback, arguments = '', function = 'dispatch', callbackType=ConnectionType.General):
		return {signal:_ConnectionDef(signal, callback, arguments, function, callbackType)}

class _ConnectionStore(object):
	def __init__(self):
		self._store = []

	def update(self, connection):
		self._store.append(connection)

	def getConnectionsBySignalName(self, signal):
		return [c for c in self._store if c.signal == signal]

	def getSignalNames(self):
		return list(set([c.signal for c in self._store]))

class StudiomaxApplication(AbstractApplication):
	# create a mapping of callbacks to be used when connecting signals
	_connectionMap = _ConnectionStore()
	_connectionMap.update(_ConnectionDef('sceneNewRequested', 'systemPreNew'))
	_connectionMap.update(_ConnectionDef('sceneNewFinished', 'systemPostNew'))
	_connectionMap.update(_ConnectionDef('sceneOpenRequested', 'filePreOpen', '""'))
	_connectionMap.update(_ConnectionDef('sceneOpenFinished', 'filePostOpen', '""'))
	_connectionMap.update(_ConnectionDef('sceneMergeRequested', 'filePreMerge'))
	_connectionMap.update(_ConnectionDef('sceneReferenceRequested', 'objectXrefPreMerge'))
	_connectionMap.update(_ConnectionDef('sceneReferenceRequested', 'sceneXrefPreMerge'))
	_connectionMap.update(_ConnectionDef('sceneMergeFinished', 'filePostMerge'))
	_connectionMap.update(_ConnectionDef('sceneReferenceFinished', 'objectXrefPostMerge'))
	_connectionMap.update(_ConnectionDef('sceneReferenceFinished', 'sceneXrefPostMerge'))
	_connectionMap.update(_ConnectionDef('sceneSaveRequested', 'filePreSave', '(if (ms_args != undefined) then (ms_args as string) else "")'))
	_connectionMap.update(_ConnectionDef('sceneSaveFinished', 'filePostSave', '(if (ms_args != undefined) then (ms_args as string) else "")'))
	_connectionMap.update(_ConnectionDef('scenePreReset', 'systemPreReset'))
	_connectionMap.update(_ConnectionDef('sceneReset', 'systemPostReset'))
	_connectionMap.update(_ConnectionDef('layerCreated', 'layerCreated'))
	_connectionMap.update(_ConnectionDef('layerDeleted', 'layerDeleted'))
	_connectionMap.update(_ConnectionDef('startupFinished', 'postSystemStartup'))
	_connectionMap.update(_ConnectionDef('shutdownStarted', 'preSystemShutdown'))
	_connectionMap.update(_ConnectionDef('sceneImportFinished', 'postImport'))
	_connectionMap.update(_ConnectionDef('selectionChanged', 'selectionSetChanged'))
	_connectionMap.update(_ConnectionDef('objectFreeze', 'nodeFreeze', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectUnfreeze', 'nodeUnfreeze', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectHide', 'nodeHide', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectUnHide', 'nodeUnHide', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectRenamed', 'nodeNameSet', '(if (ms_args != undefined) then (#(ms_args[1], ms_args[2], ms_args[3])) else #("", "", ""))', 'dispatchRename'))
	_connectionMap.update(_ConnectionDef('objectCreated', 'nodeCreated', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectCloned', 'nodeCloned', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectAdded', 'sceneNodeAdded', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectPreDelete', 'nodePreDelete', 'ms_args', 'preDelete'))
	_connectionMap.update(_ConnectionDef('objectPostDelete', 'nodePostDelete', function = 'postDelete'))
	_connectionMap.update(_ConnectionDef('objectParented', 'nodeLinked', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('objectUnparented', 'nodeUnlinked', 'ms_args', 'dispatchObject'))
	_connectionMap.update(_ConnectionDef('viewportRedrawn', '', function='dispatchFunction', callbackType=_ConnectionDef.ConnectionType.Viewport))
	
	def _connectStudiomaxSignal(self, connDef, blurdevSignal):
		"""
			\remarks	Responsible for connecting a signal to studiomax
		"""
		# store the maxscript methods needed
		_n = mxs.pyhelper.namify
		if connDef.callbackType == connDef.ConnectionType.Viewport:
			signal = _STUDIOMAX_VIEWPORT_TEMPLATE % {'function':connDef.function, 'signal':blurdevSignal}
			# Ensure that if the old signal existed it is removed before redefining it. If function is undefined it will do nothing
			mxs.unregisterRedrawViewsCallback(getattr(mxs, 'blurfn_%s' % blurdevSignal))
			mxs.execute(signal)
			mxs.registerRedrawViewsCallback(getattr(mxs, 'blurfn_%s' % blurdevSignal))
		else:
			if connDef.arguments:
				script = _STUDIOMAX_CALLBACK_TEMPLATE % { 'function':connDef.function, 'signal': blurdevSignal, 'args': connDef.arguments }
			else:
				script = _STUDIOMAX_CALLBACK_TEMPLATE_NO_ARGS % { 'function':connDef.function, 'signal': blurdevSignal }
			mxs.callbacks.addScript( _n(connDef.callback), script, id = _n('blur3dcallbacks') )
	
	def allowedCharacters(self):
		return 'A-Za-z0-9_. /+*<>=|-'

	def connect(self):
		"""
			\remarks	connect application specific callbacks to <blur3d.api.Dispatch>, dispatch will convert the native object to a blur3d.api object
						and emit a signal.
						connect is called when the first <blur3d.api.Dispatch> signal is connected.
			\return		<bool>	The Connection was successfull
		"""
		global dispatch
		import blur3d.api
		dispatch = blur3d.api.dispatch
		return super(StudiomaxApplication, self).connect()
	
	def connectCallback(self, signal):
		"""
			\remarks	Connects a single callback. This allows blur3d to only have to respond to callbacks that tools actually
						need, instead of all callbacks.
		"""
		if signal in self._connectionMap.getSignalNames():
			connections = self._connectionMap.getConnectionsBySignalName(signal)
			for object in connections:
				self._connectStudiomaxSignal(object, signal)
		else:
			debug.debugMsg('Connect: Signal %s has no signal map' % signal, debug.DebugLevel.Mid)
	
	def disconnectCallback(self, signal):
		"""
			\remarks	Disconnect a single callback when it is no longer used.
		"""
		if signal in self._connectionMap.getSignalNames():
			connections = self._connectionMap.getConnectionsBySignalName(signal)
			for connDef in connections:
				if connDef.callbackType == connDef.ConnectionType.Viewport:
					mxs.unregisterRedrawViewsCallback(getattr(mxs, 'blurfn_%s' % connDef.signal))
				else:
					namify = mxs.pyhelper.namify
					mxs.callbacks.removeScripts(namify(connDef.callback), id = namify('blur3dcallbacks'))
		else:
			debug.debugMsg('Disconnect: Signal %s has no signal map' % signal, debug.DebugLevel.Mid)
	
	def disconnect(self):
		"""
			\remarks	disconnect application specific callbacks to <blur3d.api.Dispatch>. This will be called when <blur3d.api.Dispatch> is deleted,
						disconnect is called when the last <blur3d.api.Dispatch> signal is disconnected.
		"""
		# remove normal callbacks
		blurdevid 	= mxs.pyhelper.namify('blur3dcallbacks')
		mxs.callbacks.removeScripts(id = blurdevid)
		# undefine the add callback function
		mxs.blur3daddcallback = None
		# remove the callback pointer to blur3d
		mxs.blur3d = None
		# remove viewport callbacks
		self.disconnectCallback('viewportRedraw')
		return
	
	def log(self, message):
		
		# TODO: Can't seem to access the native log message.
		print message
		return True

	def installDir(self):
		""" Returns the path to the application's install directory
		
		:return: path string
		:rtyp: str
		"""
		return mxs.pathConfig.resolvePathSymbols('$max')
	
	def preDeleteObject(self, callback, *args):
		"""
			\remarks	Pre-process the object that is going to be deleted.
		"""
		if args:
			self._objectToBeDeleted = args[0].name
	
	def postDeleteObject(self, callback, *args):
		"""
			\remarks	Emits the signal that a object has been deleted. This method is used for applications like max that generate a pre and post delete signal.
		"""
		if self._objectToBeDeleted:
			dispatch.objectDeleted.emit(self._objectToBeDeleted)
			
	def name( self ):
		return "StudioMax"
		
	def version(self, major=True):
		version = mxs.maxVersion()
		if major:
			return int(version[0] / 1000)
		else:
			return '.'.join([unicode(token) for token in version])
	
	def refresh(self):
		if not self._blockRefresh:
			mxs.completeRedraw()
			return True
		return False
		
	def year(self):
		return 1998 + self.version()

	def nameSpaceSeparator(self):
		return '.'

	def animationClipExtension(self):
		return 'xaf'
		
	def sceneFileExtension(self):
		return 'max'

	def modelFileExtension(self):
		return self.sceneFileExtension()

	def nameAndVersion( self ):
		version = mxs.maxVersion()
		jobTypeDic = {
				'5100' : "Max5",
				'6000':	 "Max6",
				'7000':	 "Max7",
				'8000':  "Max8",
				'9000':  "Max9",
				'10000': "Max10",
				'11000': "Max2009",
				'12000': "Max2010",
				'14000': "Max2012",
				'16000': "Max2014",
				'default': "Max2014"}
		if jobTypeDic.has_key(str(version[0])):
			jobType = jobTypeDic[str(version[0])]
		else:
			jobType = jobTypeDic['default']

		return jobType
		
	def id(self):
		"""
			\remarks	implements AbstractScene.softwareId to return a unique version/bits string information that will represent the exact
									version of the software being run.
			\return		<str>
		"""
		mversion 	= mxs.maxVersion()[0]/1000
		sixtyfour	= ''
		if ( mversion > 10 ):
			mversion = 2009 + (mversion-11)		# shifted to years at version 11
		if ( mxs.is64BitApplication() ):
			sixtyfour = '_64'
		return 'MAX%i%s' % (mversion,sixtyfour)
	
# register the symbol
from blur3d import api
api.registerSymbol( 'Application', StudiomaxApplication)

# Creating a single instance of Application for all code to use.
api.registerSymbol( 'application', StudiomaxApplication())