
# Copyright 2014 Citrix Systems
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import requests

from neutron_lib import exceptions as n_exc
from oslo_log import log as logging
from oslo_serialization import jsonutils

from neutron_lbaas._i18n import _

LOG = logging.getLogger(__name__)

CONTENT_TYPE_HEADER = 'Content-type'
ACCEPT_HEADER = 'Accept'
AUTH_HEADER = 'Cookie'
DRIVER_HEADER = 'X-OpenStack-LBaaS'
TENANT_HEADER = 'X-Tenant-ID'
JSON_CONTENT_TYPE = 'application/json'
DRIVER_HEADER_VALUE = 'netscaler-openstack-lbaas'
NITRO_LOGIN_URI = 'nitro/v2/config/login'


class NCCException(n_exc.NeutronException):

    """Represents exceptions thrown by NSClient."""

    CONNECTION_ERROR = 1
    REQUEST_ERROR = 2
    RESPONSE_ERROR = 3
    UNKNOWN_ERROR = 4

    def __init__(self, error, status=requests.codes.SERVICE_UNAVAILABLE):
        self.message = _("NCC Error %d") % error
        super(NCCException, self).__init__()
        self.error = error
        self.status = status

    def is_not_found_exception(self):
        if int(self.status) == requests.codes.NOT_FOUND:
            return True


class NSClient(object):

    """Client to operate on REST resources of NetScaler Control Center."""

    def __init__(self, service_uri, username, password,
                 ncc_cleanup_mode="False"):
        if not service_uri:
            LOG.exception("No NetScaler Control Center URI specified. "
                          "Cannot connect.")
            raise NCCException(NCCException.CONNECTION_ERROR)
        self.service_uri = service_uri.strip('/')
        self.auth = None
        self.cleanup_mode = False
        if username and password:
            self.username = username
            self.password = password
        if ncc_cleanup_mode.lower() == "true":
            self.cleanup_mode = True

    def create_resource(self, tenant_id, resource_path, object_name,
                        object_data):
        """Create a resource of NetScaler Control Center."""
        return self._resource_operation('POST', tenant_id,
                                        resource_path,
                                        object_name=object_name,
                                        object_data=object_data)

    def is_login(self, resource_uri):
        if 'login' in resource_uri.lower():
            return True
        else:
            return False

    def login(self):
        """Get session based login"""
        login_obj = {"username": self.username, "password": self.password}

        msg = "NetScaler driver login:" + repr(self.username)
        LOG.info(msg)
        resp_status, result = self.create_resource("login", NITRO_LOGIN_URI,
                                                   "login", login_obj)
        LOG.info("Response: status : %(status)s %result(result)s", {
                "status": resp_status, "result": result['body']})
        result_body = jsonutils.loads(result['body'])

        session_id = None
        if result_body and "login" in result_body:
            logins = result_body["login"]
            if isinstance(logins, list):
                login = logins[0]
            else:
                login = logins
            if login and "sessionid" in login:
                session_id = login["sessionid"]

        if session_id:
            LOG.info("Response: %(result)s", {"result": result['body']})
            LOG.info(
                "Session_id = %(session_id)s" %
                {"session_id": session_id})
            # Update sessin_id in auth
            self.auth = "SessId=%s" % session_id
        else:
            raise NCCException(NCCException.RESPONSE_ERROR)

    def retrieve_resource(self, tenant_id, resource_path, parse_response=True):
        """Retrieve a resource of NetScaler Control Center."""
        return self._resource_operation('GET', tenant_id, resource_path)

    def update_resource(self, tenant_id, resource_path, object_name,
                        object_data):
        """Update a resource of the NetScaler Control Center."""
        return self._resource_operation('PUT', tenant_id,
                                        resource_path,
                                        object_name=object_name,
                                        object_data=object_data)

    def remove_resource(self, tenant_id, resource_path, parse_response=True):
        """Remove a resource of NetScaler Control Center."""
        if self.cleanup_mode:
            return True
        else:
            return self._resource_operation('DELETE', tenant_id, resource_path)

    def _resource_operation(self, method, tenant_id, resource_path,
                            object_name=None, object_data=None):
        resource_uri = "%s/%s" % (self.service_uri, resource_path)
        if not self.auth and not self.is_login(resource_uri):
            # Creating a session for the first time
            self.login()
        headers = self._setup_req_headers(tenant_id)
        request_body = None
        if object_data:
            if isinstance(object_data, str):
                request_body = object_data
            else:
                obj_dict = {object_name: object_data}
                request_body = jsonutils.dumps(obj_dict)
        try:
            response_status, resp_dict = (self.
                                          _execute_request(method,
                                                           resource_uri,
                                                           headers,
                                                           body=request_body))
        except NCCException as e:
            if e.status == requests.codes.NOT_FOUND and method == 'DELETE':
                return 200, {}
            else:
                raise e

        return response_status, resp_dict

    def _is_valid_response(self, response_status):
        # when status is less than 400, the response is fine
        return response_status < requests.codes.bad_request

    def _setup_req_headers(self, tenant_id):
        headers = {ACCEPT_HEADER: JSON_CONTENT_TYPE,
                   CONTENT_TYPE_HEADER: JSON_CONTENT_TYPE,
                   DRIVER_HEADER: DRIVER_HEADER_VALUE,
                   TENANT_HEADER: tenant_id,
                   AUTH_HEADER: self.auth}
        return headers

    def _get_response_dict(self, response):
        response_dict = {'status': int(response.status_code),
                         'body': response.text,
                         'headers': response.headers}
        if self._is_valid_response(int(response.status_code)):
            if response.text:
                response_dict['dict'] = response.json()
        return response_dict

    def _execute_request(self, method, resource_uri, headers, body=None):
        service_uri_dict = {"service_uri": self.service_uri}
        try:
            response = requests.request(method, url=resource_uri,
                                        headers=headers, data=body)
        except requests.exceptions.SSLError:
            LOG.exception("SSL error occurred while connecting "
                         "to %(service_uri)s",
                         service_uri_dict)
            raise NCCException(NCCException.CONNECTION_ERROR)
        except requests.exceptions.ConnectionError:
            LOG.exception("Connection error occurred while connecting"
                         "to %(service_uri)s", service_uri_dict)
            raise NCCException(NCCException.CONNECTION_ERROR)

        except requests.exceptions.Timeout:
            LOG.exception(
                "Request to %(service_uri)s timed out", service_uri_dict)
            raise NCCException(NCCException.CONNECTION_ERROR)
        except (requests.exceptions.URLRequired,
                requests.exceptions.InvalidURL,
                requests.exceptions.MissingSchema,
                requests.exceptions.InvalidSchema):
            LOG.exception("Request did not specify a valid URL")
            raise NCCException(NCCException.REQUEST_ERROR)
        except requests.exceptions.TooManyRedirects:
            LOG.exception("Too many redirects occurred for request ")
            raise NCCException(NCCException.REQUEST_ERROR)
        except requests.exceptions.RequestException:
            LOG.exception(
                "A request error while connecting to %(service_uri)s",
                service_uri_dict)
            raise NCCException(NCCException.REQUEST_ERROR)
        except Exception:
            LOG.exception(
                "A unknown error occurred during request to"
                " %(service_uri)s", service_uri_dict)
            raise NCCException(NCCException.UNKNOWN_ERROR)
        resp_dict = self._get_response_dict(response)
        resp_body = resp_dict['body']
        LOG.info("Response: %(resp_body)s", {"resp_body": resp_body})
        response_status = resp_dict['status']
        if response_status == requests.codes.unauthorized:
            LOG.exception("Unable to login. Invalid credentials passed."
                         "for: %s", self.service_uri)
            if not self.is_login(resource_uri):
                # Session expired, relogin and retry....
                self.login()
                # Retry the operation
                headers.update({AUTH_HEADER: self.auth})
                self._execute_request(method,
                                      resource_uri,
                                      headers,
                                      body)
            else:
                raise NCCException(NCCException.RESPONSE_ERROR)
        if not self._is_valid_response(response_status):
            response_msg = resp_body
            response_dict = {"method": method,
                             "url": resource_uri,
                             "response_status": response_status,
                             "response_msg": response_msg}
            LOG.exception("Failed %(method)s operation on %(url)s "
                         "status code: %(response_status)s "
                         "message: %(response_msg)s", response_dict)
            raise NCCException(NCCException.RESPONSE_ERROR, response_status)
        return response_status, resp_dict
