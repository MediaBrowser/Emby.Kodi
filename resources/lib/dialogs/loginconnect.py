# -*- coding: utf-8 -*-

##################################################################################################

import logging
import os

import xbmcgui
import xbmcaddon

from utils import language as lang

##################################################################################################

log = logging.getLogger("EMBY."+__name__)
addon = xbmcaddon.Addon('plugin.video.emby')

ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_BACK = 92
SIGN_IN = 200
CANCEL = 201
ERROR_TOGGLE = 202
ERROR_MSG = 203
USER = 204
PASSWORD = 205
ERROR = {
    'Invalid': 1,
    'Empty': 2
}

##################################################################################################


class LoginConnect(xbmcgui.WindowXMLDialog):

    _user = None
    error = None


    def __init__(self, *args, **kwargs):

        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def set_connect_manager(self, connect_manager):
        self.connect_manager = connect_manager

    def is_logged_in(self):
        return True if self._user else False

    def get_user(self):
        return self._user


    def onInit(self):

        self.user_field = self.getControl(USER)
        self.setFocus(self.user_field)
        self.password_field = self.getControl(PASSWORD)
        self.signin_button = self.getControl(SIGN_IN)
        self.remind_button = self.getControl(CANCEL)
        self.error_toggle = self.getControl(ERROR_TOGGLE)
        self.error_msg = self.getControl(ERROR_MSG)

    def onClick(self, control):

        if control == SIGN_IN:
            # Sign in to emby connect
            self._disable_error()

            user = self.user_field.getText()
            password = self.password_field.getText()

            if not user or not password:
                # Display error
                self._error(ERROR['Empty'], lang(30608))
                log.error("Username or password cannot be null")

            elif self._login(user, password):
                self.close()

        elif control == CANCEL:
            # Remind me later
            self.close()

    def onAction(self, action):

        if (self.error == ERROR['Empty']
                and self.user_field.getText() and self.password_field.getText()):
            self._disable_error()

        if action in (ACTION_BACK, ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU):
            self.close()

    def _login(self, username, password):

        result = self.connect_manager.loginToConnect(username, password)
        if result is False:
            self._error(ERROR['Invalid'], lang(33009))
            return False
        else:
            self._user = result
            return True

    def _error(self, state, message):

        self.error = state
        self.error_msg.setLabel(message)
        self.error_toggle.setVisibleCondition('True')

    def _disable_error(self):

        self.error = None
        self.error_toggle.setVisibleCondition('False')
