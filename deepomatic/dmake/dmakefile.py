import os
from deepomatic.dmake.serializer import ValidationError, YAML2PipelineSerializer
from deepomatic.dmake.common import DMakeException

###############################################################################

class DMakeFile(YAML2PipelineSerializer):
    def __init__(self, file, data):
        super(DMakeFile, self).__init__()

        self.__path__ = os.path.join(os.path.dirname(file), '')
        self.__data__ = data

    def validate(self):
        # Run the YAML2PipelineSerializer validation
        try:
            self._validate_(self.__path__, self.__data__)
        except ValidationError as e:
            raise DMakeException(("Error in %s:\n" % file) + str(e))
        self.__post_validate__()

    # def trigger_action(action_manager, action, service = None):
    #     template = action_manager.get_action(action)
    #     raise Exception("__get_services__ needs to be overloaded")

    """
        This MUST BE OVERLOADED and need to return the application name.
    """
    def get_app_name():
        raise Exception("get_app_name needs to be overloaded")

    """
        This MUST BE OVERLOADED and need to return the list of services
        without the application name.
    """
    def get_services():
        raise Exception("__get_services__ needs to be overloaded")

    def __post_validate__(self):
        pass # function to be overloaded if some post-processing is needed

    def __str__(self):
        return self.__path__


1 list files
2 find active files (if no app specified or no *)

