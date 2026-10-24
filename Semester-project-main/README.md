# Fintr break-even tool (BFB 321, Group 9): Steps 1-2
Run: `pip install -r requirements.txt`, then `python -m pytest` (model tests) and `python app.py` (http://127.0.0.1:5000).
- `models/breakeven.py`: standalone model (formulae, units and assumptions in the module docstring)
- `tests/`: unit tests against hand-worked examples
- `app.py` + `templates/` + `static/`: Bootstrap frontend (temporary direct calls to the model; Step 4 adds REST endpoints and MySQL)
Sample values are illustrative placeholders. Replace with Fintr's actual data.
