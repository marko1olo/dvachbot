import asyncio
import sys
import os
import inspect

sys.stdout.reconfigure(encoding='utf-8')

# Put root directory in sys.path
root_dir = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, root_dir)

def test_r2_format_header_imports_and_definitions():
    print("=== R2 EMPIRICAL TEST: format_header imports & execution ===")
    
    # 1. Test importing format_header from post_helpers
    import post_helpers
    assert hasattr(post_helpers, "format_header"), "post_helpers must have format_header"
    assert inspect.iscoroutinefunction(post_helpers.format_header), "format_header must be an async coroutine function"
    print("  -> post_helpers.format_header exists and is async coroutine function")
    
    # 2. Test importing user_manager and checking format_header presence in its globals
    import user_manager
    assert "format_header" in user_manager.__dict__, "format_header must be imported in user_manager namespace"
    assert user_manager.format_header is post_helpers.format_header, "user_manager.format_header must reference post_helpers.format_header"
    print("  -> user_manager.py has format_header correctly imported in module namespace")
    
    # 3. Check site_tgach/main.py
    import site_tgach.main as main_mod
    assert hasattr(main_mod, "format_header"), "site_tgach/main.py must have format_header"
    print("  -> site_tgach/main.py has format_header correctly imported")
    
    # 4. Check ai_manager.py
    import ai_manager
    assert hasattr(ai_manager, "format_header"), "ai_manager.py must have format_header"
    print("  -> ai_manager.py has format_header correctly imported")
    
    # 5. Check bot_helpers.py
    import bot_helpers
    assert hasattr(bot_helpers, "format_header"), "bot_helpers.py must have format_header"
    print("  -> bot_helpers.py has format_header correctly imported")

    # 6. Execute format_header coroutine with mock/sample data
    async def run_format_header_execution_test():
        # Mock _format_header_inner or DB calls if needed
        from unittest.mock import patch, AsyncMock
        with patch("post_helpers._format_header_inner", new_callable=AsyncMock) as mock_inner:
            mock_inner.return_value = "#100 Anonymous"
            res = await post_helpers.format_header("b", 100)
            assert res == "#100 Anonymous", f"Expected '#100 Anonymous', got '{res}'"
            
            # Call via user_manager's reference
            res_um = await user_manager.format_header("b", 100)
            assert res_um == "#100 Anonymous"
            print("  -> format_header executed successfully without NameError!")

    asyncio.run(run_format_header_execution_test())
    print("\n[SUCCESS] R2 FORMAT_HEADER IMPORT & EXECUTION TEST PASSED 100%!")

if __name__ == "__main__":
    test_r2_format_header_imports_and_definitions()
