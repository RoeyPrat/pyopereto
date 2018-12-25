from pyopereto.client import OperetoClient
import sys, traceback

class MyService():

    def __init__(self):
        self.client = OperetoClient()
        self.input = self.client.input
        print self.input

    def run(self):
        try:
            ## print the input parameter
            print 'The input parameters passed: %s'%str(self.input['my_input_param'])

            ## modify output parameter with input one
            self.client.modify_process_property('my_output_param', self.input['my_input_param'])

            ## verify that input text started with Hello World
            if not self.input['my_input_param'].startswith('Hello World'):
                print >> sys.stderr, 'Input does not start with Hello World'
                return self.client.FAILURE

            return self.client.SUCCESS
        except:
            traceback.format_exc()
            return self.client.FAILURE

if __name__ == "__main__":
    exit(MyService().run())