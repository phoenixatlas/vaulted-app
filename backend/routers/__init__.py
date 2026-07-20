"""Router package for the Vaulted backend.

Each file in this package defines a single FastAPI `APIRouter` that is
mounted onto the top-level `/api` router in server.py via
`api.include_router(<router>)`. This keeps server.py itself small and lets
us test individual route groups in isolation.
"""
