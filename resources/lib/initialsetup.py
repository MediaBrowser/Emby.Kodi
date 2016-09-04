# -*- coding: utf-8 -*-

#################################################################################################

import logging

import xbmc
import xbmcgui

import clientinfo
import connectmanager
import connect.connectionmanager as connectionmanager
import downloadutils
import userclient
from utils import settings, language as lang, passwordsXML

#################################################################################################

log = logging.getLogger("EMBY."+__name__)
STATE = connectionmanager.ConnectionState

#################################################################################################


class InitialSetup(object):


    def __init__(self):

        self.addonId = clientinfo.ClientInfo().getAddonId()
        self.doUtils = downloadutils.DownloadUtils().downloadUrl
        self.userClient = userclient.UserClient()
        self.connectmanager = connectmanager.ConnectManager()


    def setup(self):
        # Check server, user, direct paths, music, direct stream if not direct path.
        addonId = self.addonId
        dialog = xbmcgui.Dialog()

        ##### SERVER INFO #####
        
        log.debug("Initial setup called.")

        ###$ Begin transition phase $###
        if settings('server') == "":
            current_server = self.userClient.get_server()
            current_userid = self.userClient.get_userid()
            current_token = self.userClient.get_token()
            self.connectmanager.get_server(current_server)
        ###$ End transition phase $###

        current_state = self.connectmanager.get_state()
        if current_state['State'] == STATE['SignedIn']:
            server = current_state['Servers'][0]
            server_address = self.connectmanager.get_address(server)
            self._set_server(server_address, server['Name'])
            self._set_user(server['UserId'], server['AccessToken'])
            return

        try:
            server = self.connectmanager.select_servers()
            log.info("Server: %s" % server)
        
        except RuntimeError as e:
            log.exception(e)
            xbmc.executebuiltin('Addon.OpenSettings(%s)' % addonId)
            return

        else:
            server_address = self.connectmanager.get_address(server)
            self._set_server(server_address, server['Name'])

            if not server.get('AccessToken') and not server.get('UserId'):
                try:
                    user = self.connectmanager.login(server)
                    log.info("User authenticated: %s" % user)
                except RuntimeError as e:
                    log.exception(e)
                    xbmc.executebuiltin('Addon.OpenSettings(%s)' % addonId)
                    return
                settings('username', value=user['User']['Name'])
                self._set_user(user['User']['Id'], user['AccessToken'])
            else:
                user = self.connectmanager.get_state()
                settings('connectUsername', value=user['ConnectUser']['Name'])
                self._set_user(server['UserId'], server['AccessToken'])

        ##### ADDITIONAL PROMPTS #####

        directPaths = dialog.yesno(
                            heading=lang(30511),
                            line1=lang(33035),
                            nolabel=lang(33036),
                            yeslabel=lang(33037))
        if directPaths:
            log.info("User opted to use direct paths.")
            settings('useDirectPaths', value="1")

            # ask for credentials
            credentials = dialog.yesno(
                                heading=lang(30517),
                                line1= lang(33038))
            if credentials:
                log.info("Presenting network credentials dialog.")
                passwordsXML()
        
        musicDisabled = dialog.yesno(
                            heading=lang(29999),
                            line1=lang(33039))
        if musicDisabled:
            log.info("User opted to disable Emby music library.")
            settings('enableMusic', value="false")
        else:
            # Only prompt if the user didn't select direct paths for videos
            if not directPaths:
                musicAccess = dialog.yesno(
                                    heading=lang(29999),
                                    line1=lang(33040))
                if musicAccess:
                    log.info("User opted to direct stream music.")
                    settings('streamMusic', value="true")

    @classmethod
    def _set_server(cls, server, name):

        settings('serverName', value=name)
        settings('server', value=server)
        log.info("Saved server information: %s", server)

    @classmethod
    def _set_user(cls, user_id, token):

        settings('userId', value=user_id)
        settings('token', value=token)
