"""Génère un mini jeu Instacart synthétique (même schéma) pour tester la chaîne sans Kaggle."""
import csv
import random
from pathlib import Path

out = Path(__file__).resolve().parents[1] / "data" / "external" / "instacart"
out.mkdir(parents=True, exist_ok=True)
random.seed(42)


def write(name, header, rows):
    with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


write("aisles", ["aisle_id", "aisle"], [(1, "fresh fruits"), (2, "yogurt"), (3, "bread")])
write("departments", ["department_id", "department"], [(1, "produce"), (2, "dairy eggs"), (3, "bakery")])
products = [(i, f"Product {i}", (i % 3) + 1, (i % 3) + 1) for i in range(1, 51)]
write("products", ["product_id", "product_name", "aisle_id", "department_id"], products)
orders, prior, train = [], [], []
oid = 0
for user in range(1, 101):
    for n in range(1, random.randint(3, 8)):
        oid += 1
        last = n == 1
        eval_set = "prior"
        orders.append((oid, user, eval_set, n, random.randint(0, 6), random.randint(7, 21),
                       "" if last else random.randint(1, 30)))
        for pos, pid in enumerate(random.sample(range(1, 51), random.randint(2, 8)), 1):
            prior.append((oid, pid, pos, random.randint(0, 1)))
write("orders", ["order_id", "user_id", "eval_set", "order_number", "order_dow",
                 "order_hour_of_day", "days_since_prior_order"], orders)
head = ["order_id", "product_id", "add_to_cart_order", "reordered"]
write("order_products__prior", head, prior)
write("order_products__train", head, prior[:20])
print(f"Échantillon écrit dans {out} ({len(orders)} commandes)")
