"""
Healthcare setup package.
Provides utilities and configuration for Healthcare module setup.
"""

def setup():
	"""
	Healthcare app install hook.
	This function is called when the Healthcare app is installed.
	"""
	# Import here to avoid circular dependencies
	from healthcare.setup.default_success_action import get_default_success_action
	
	# Future: Add any app-install specific setup here
	# For now, this is a placeholder that can be extended
	
	# Return success action for setup wizard
	return get_default_success_action()
