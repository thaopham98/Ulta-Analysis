import json
import requests

# url = ( # test 1
#     "https://www.ulta.com/p/"
#     "cheek-thrills-multi-finish-face-trio-pimprod2051122"
#     "?sku=2638344"
# )
# url = ( #test 2
    # "https://www.ulta.com/p/"
    # "desert-island-duo-blush-bronzer-stick-pimprod2047137"
    # "?sku=2628524"
# 
url = ( # test 3
    "https://www.ulta.com/p/"
    "desert-island-duo-blush-bronzer-stick-pimprod2047137"
    "?sku=2628525"
)

response = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30,
)
response.raise_for_status()
html = response.text

marker = "window.__APOLLO_STATE__"
start = html.index(marker)
json_start = html.index("{", start)

state, _ = json.JSONDecoder().raw_decode(html[json_start:])


def find_ingredients(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "ingredients" and isinstance(child, str):
                yield child
            yield from find_ingredients(child)
    elif isinstance(value, list):
        for child in value:
            yield from find_ingredients(child)


ingredients = list(find_ingredients(state))
print(ingredients[0] if ingredients else "No ingredients found")