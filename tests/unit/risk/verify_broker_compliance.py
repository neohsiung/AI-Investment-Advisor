
import unittest
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Type
import inspect
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.domain.broker import IBroker
from src.services.etoro_service import EtoroService
from src.services.futu_service import FutuService
from src.domain.trading import Order, OrderAction

class BrokerContractTest(unittest.TestCase):
    """
    Contract Test Suite for IBroker Implementations.
    Ensures any new broker strictly follows the interface and security guidelines.
    """

    def verify_broker_compliance(self, broker_class: Type[IBroker]):
        """
        Verify that a broker class implements all required methods and properties.
        """
        instance = broker_class()
        
        # 1. Interface Compliance
        self.assertIsInstance(instance, IBroker, f"{broker_class.__name__} must inherit from IBroker")
        
        required_methods = [
            'get_name',
            'get_account',
            'get_positions',
            'get_history',
            'execute_order',
            'sync_history'
        ]
        
        for method in required_methods:
            # Check methods exist
            self.assertTrue(hasattr(instance, method), f"{broker_class.__name__} missing method: {method}")
            # Check they are callable
            attr = getattr(instance, method)
            self.assertTrue(callable(attr), f"{method} in {broker_class.__name__} must be callable")

        # 2. Security Checks (Static Analysis via Inspection)
        # Check for hardcoded credentials in __init__ defaults
        try:
            init_params = inspect.signature(broker_class.__init__).parameters
            for param in init_params.values():
                name_lower = param.name.lower()
                if ('password' in name_lower or 'key' in name_lower or 'secret' in name_lower or 'token' in name_lower):
                    if param.default != inspect.Parameter.empty and param.default is not None:
                         # Allow None or empty string as safe defaults, but not actual values
                         if isinstance(param.default, str) and len(param.default) > 0:
                             self.fail(f"SECURITY RISK: {broker_class.__name__} has hardcoded default for sensitive param '{param.name}'")
        except ValueError:
            pass # Signature might fail for some built-ins or wrappers

    def test_etoro_compliance(self):
        self.verify_broker_compliance(EtoroService)

    def test_futu_compliance(self):
        self.verify_broker_compliance(FutuService)

if __name__ == '__main__':
    unittest.main()
