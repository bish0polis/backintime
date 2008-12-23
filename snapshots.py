#    Back In Time
#    Copyright (C) 2008 Oprea Dan
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import os
import os.path
import datetime
import gettext
import statvfs

import config
import logger
import applicationinstance


_=gettext.gettext


class Snapshots:
	def __init__( self, cfg = None ):
		self.config = cfg
		if self.config is None:
			self.config = config.Config()

	def get_snapshot_id( self, date ):
		if type( date ) is datetime.datetime:
			return date.strftime( '%Y%m%d-%H%M%S' )

		if type( date ) is datetime.date:
			return date.strftime( '%Y%m%d-000000' )

		if type( date ) is str:
			return date
		
		return ""

	def get_snapshot_path( self, date ):
		return os.path.join( self.config.get_snapshots_full_path(), self.get_snapshot_id( date ) )

	def _get_snapshot_data_path( self, snapshot_id ):
		if len( snapshot_id ) <= 1:
			return '/';
		return os.path.join( self.get_snapshot_path( snapshot_id ), 'backup' )
	
	def get_snapshot_path_to( self, snapshot_id, toPath = '/' ):
		return os.path.join( self._get_snapshot_data_path( snapshot_id ), toPath[ 1 : ] )

	def get_snapshot_display_id( self, snapshot_id ):
		if len( snapshot_id ) <= 1:
			return _('Now')
		return "%s-%s-%s %s:%s:%s" % ( snapshot[ 0 : 4 ], snapshot[ 4 : 6 ], snapshot[ 6 : 8 ], snapshot[ 9 : 11 ], snapshot[ 11 : 13 ], snapshot[ 13 : 15 ]  )
	
	def get_snapshot_display_name_gtk( self, snapshot_id ):
		display_name = self.get_snapshot_display_id( snapshot_id )
		name = self.get_snapshot_name( snapshot_id )
		if len( name ) > 0:
			display_name = display_name + ' - <b>' + name + '</b>'
		return display_name

	def get_snapshot_name( self, snapshot_id ):
		if len( snapshot_id ) <= 1: #not a snapshot
			return ''

		path = self.get_snapshot_path( snapshot_id )
		if not os.path.isdir( path ):
			return ''
		
		name = ''
		try:
			file = open( os.path.join( path, 'name' ), 'rt' )
			name = file.read()
			file.close()
		except:
			pass

		return name

	def set_snapshot_name( self, snapshot_id, name ):
		if len( snapshot_id ) <= 1: #not a snapshot
			return

		path = self.get_snapshot_path( snapshot_id )
		if not os.path.isdir( path ):
			return

		name_path = os.path.join( path, 'name' )

		os.system( "chmod a+w \"%s\"" % path )

		try:
			file = open( name_path, 'wt' )
			file.write( name )
			file.close()
		except:
			pass

		os.system( "chmod a-w \"%s\"" % path )

	def is_busy( self ):
		instance = applicationinstance.ApplicationInstance( self.config.get_take_snapshot_instance_file(), False )
		return not instance.check()

	def restore( self, snapshot_id, path ):
		logger.info( "Restore: %s" % path )
		backup_suffix = '.backup.' + datetime.date.today().strftime( '%Y%m%d' )
		cmd = "rsync -avR --copy-unsafe-links --backup --suffix=%s --one-file-system --chmod=+w %s/.%s %s" % ( backup_suffix, self.config.get_snapshot_path_to( snapshot_id ), path, '/' )
		self._execute( cmd )

	def get_snapshots_list( self, sort_reverse = True ):
		biglist = []
		snapshots_path = self.config.get_snapshots_full_path()

		try:
			biglist = os.listdir( snapshots_path )
		except:
			pass

		list = []
		
		for item in biglist:
			if len( item ) != 15:
				continue
			if os.path.isdir( os.path.join( snapshots_path, item ) ):
				list.append( item )

		list.sort( reverse = sort_reverse )
		return list

	def remove_snapshot( self, snapshot_id ):
		if len( snapshot_id ) <= 1:
			return

		path = self.get_snapshot_path( snapshot_id )
		cmd = "chmod -R a+w \"%s\"" %  path
		self._execute( cmd )
		cmd = "rm -rf \"%s\"" % path
		self._execute( cmd )

	def take_snapshot( self ):
		if not self.config.can_backup():
			logger.warning( 'Not configured or backup path don\'t exists' )
			return False

		instance = applicationinstance.ApplicationInstance( self.config.get_take_snapshot_instance_file(), False )
		if not instance.check():
			logger.warning( 'A backup is already running' )
			return False

		instance.start_application()
		
		logger.info( 'Lock' )

		ret_val = False
	
		snapshot_id = self.get_snapshot_id( datetime.datetime.today() )
		snapshot_path = self.get_snapshot_path( snapshot_id )

		if os.path.exists( snapshot_path ):
			logger.warning( "Snapshot path \"%s\" already exists" % snapshot_path )
			retVal = True
		else:
			#try:
			ret_val = self._take_snapshot( snapshot_id )
			#except:
			#	retVal = False

		if not ret_val:
			os.system( "rm -rf \"%s\"" % snapshot_path )
			logger.warning( "No new snapshot (not needed or error)" )
		
		#try:
		self._free_space()
		#except:
		#	pass

		os.system( 'sleep 2' ) #max 1 backup / second

		instance.exit_application()
		logger.info( 'Unlock' )
		return ret_val

	def _take_snapshot( self, snapshot_id ):
		snapshot_path = self.get_snapshot_path( snapshot_id )
		snapshot_path_to = self.get_snapshot_path_to( snapshot_id )

		#check only existing paths
		all_include_folders = self.config.get_include_folders().split( ':' )
		include_folders = []
		for folder in all_include_folders:
			if os.path.isdir( folder ):
				include_folders.append( folder )

		#create exclude patterns string
		rsync_exclude = ''
		for exclude in self.config.get_exclude_patterns().split( ':' ):
			rsync_exclude += " --exclude=\"%s\"" % exclude

		#check previous backup
		changed_folders = include_folders 
		snapshots = self.get_snapshots_list()

		if len( snapshots ) > 0:
			prev_snapshot_id = snapshots[0]
			logger.info( "Compare with old snapshot: %s" % prev_snapshot_id )

			changed_folders = []

			#check for changes
			for folder in include_folders:
				prev_snapshot_folder = self.get_snapshot_path_to( prev_snapshot_id, folder )

				if os.path.isdir( prev_snapshot_folder ):
					cmd = "diff -qr " + rsync_exclude + " \"%s/\" \"%s/\"" % ( folder, prev_snapshot_folder )
					if len( self._execute_output( cmd ) ) > 0:
						changed_folders.append( folder )
				else: #folder don't exists in backup
					changed_folders.append( folder )

			#check if something changed
			if len( changed_folders ) == 0:
				logger.info( "Nothing changed, no back needed" )
				return False
		
			#create hard links
			logger.info( "Create hard-links" )
			self._execute( "mkdir -p \"%s\"" % snapshot_path_to )
			cmd = "cp -al \"%s/\"* \"%s\"" % ( self.get_snapshot_path_to( prev_snapshot_id ), snapshot_path_to )
			self._execute( cmd )
			cmd = "chmod -R a+w \"%s\"" % snapshot_path
			self._execute( cmd )

		#create new backup folder
		self._execute( "mkdir -p \"%s\"" % snapshot_path_to )
		if not os.path.exists( snapshot_path_to ):
			logger.error( "Can't create snapshot directory: %s" % snapshot_path_to )
			return False

		#sync changed folders
		for folder in changed_folders:
			snapshot_folder = self.get_snapshot_path_to( snapshot_id, folder )
			self._execute( "mkdir -p \"%s\"" % snapshot_folder )
			cmd = "rsync -av --copy-unsafe-links --delete --one-file-system " + rsync_exclude + " \"%s/\" \"%s/\"" % ( folder, snapshot_folder )
			logger.info( "Call rsync for directory: %s" % folder )
			self._execute( cmd )

		#make new folder read-only
		self._execute( "chmod -R a-w \"%s\"" % snapshot_path )
		return True

	def _free_space( self ):
		#remove old backups
		if self.config.is_remove_old_snapshots_enabled():
			snapshots = self.get_snapshots_list( False )

			old_backup_id = self.get_snapshot_id( self.config.get_remove_old_snapshots_date() )
			logger.info( "Remove backups older then: %s" % old_backup_id )

			while True:
				if len( snapshots ) <= 1:
					break

				if snapshots[0] >= old_backup_id:
					break

				if self.config.get_dont_remove_named_snapshots():
					if len( self.get_snapshot_name( snapshots[0] ) ) > 0:
						del snapshots[0]
						continue

				self.remove_snapshot( snapshots[0] )
				del snapshots[0]

		#try to keep min free space
		if self.config.is_min_free_space_enabled():
			min_free_space = self.config.get_min_free_space_in_mb()

			logger.info( "Keep min free disk space: %s Mb" % min_free_space )

			snapshots = self.get_snapshots_list( False )

			while True:
				if len( snapshots ) <= 1:
					break

				info = os.statvfs( self.config.get_snapshots_path() )
				free_space = info[ statvfs.F_FRSIZE ] * info[ statvfs.F_BAVAIL ] / ( 1024 * 1024 )

				if free_space >= min_free_space:
					break

				if self.config.get_dont_remove_named_snapshots():
					if len( self.get_snapshot_name( snapshots[0] ) ) > 0:
						del snapshots[0]
						continue

				self.remove_snapshot( snapshots[0] )
				del snapshots[0]

	def _execute( self, cmd ):
		ret_val = os.system( cmd )

		if ret_val != 0:
			logger.warning( "Command \"%s\" returns %s" % ( cmd, ret_val ) )
		else:
			logger.info( "Command \"%s\" returns %s" % ( cmd, ret_val ) )

		return ret_val

	def _execute_output( self, cmd ):
		pipe = os.popen( cmd, 'r' )
		output = pipe.read()
		ret_val = pipe.close()

		if ret_val is None:
			ret_val = 0

		if ret_val != 0:
			logger.warning( "Command \"%s\" returns %s" % ( cmd, ret_val ) )
		else:
			logger.info( "Command \"%s\" returns %s" % ( cmd, ret_val ) )

		return output


if __name__ == "__main__":
	config = config.Config()
	snapshots = Snapshots( config )
	snapshots.take_snapshot()
