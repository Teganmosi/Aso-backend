from django.core.management.base import BaseCommand
from apps.products.models import Category


class Command(BaseCommand):
    help = 'Seeds comprehensive Nigerian Fashion Marketplace category tree hierarchy'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding category hierarchy..."))

        categories_data = [
            {
                'name': 'Men',
                'description': 'Men\'s fashion, traditional attire, senators, suits, and contemporary wear.',
                'display_order': 1,
                'children': [
                    {'name': 'Agbada & Grand Native Sets', 'description': 'Grand Agbada sets and traditional ceremonial attire.', 'display_order': 1},
                    {'name': 'Men\'s Two-Piece Senator Suits', 'description': 'Senator sets, two-piece co-ords, and tailored tunics.', 'display_order': 2},
                    {'name': 'Kaftans & Tunics', 'description': 'Classic Nigerian kaftans and stylish casual traditional wear.', 'display_order': 3},
                    {'name': 'Men\'s Suits & Blazers', 'description': 'Tailored corporate blazers, native suits, and formal jackets.', 'display_order': 4},
                    {'name': 'Men\'s Streetwear & Casuals', 'description': 'Urban Nigerian streetwear, graphic tees, and jackets.', 'display_order': 5},
                ]
            },
            {
                'name': 'Women',
                'description': 'Women\'s fashion, suits, traditional wear, gowns, and bespoke tailoring.',
                'display_order': 2,
                'children': [
                    {'name': 'Women\'s Suits & Blazers', 'description': 'Tailored female corporate suits, executive blazers, and luxury native pant suits.', 'display_order': 1},
                    {'name': 'Female Senator & Two-Piece Sets', 'description': 'Co-ord sets, tailored female senator suits, tunics, and matching ensembles.', 'display_order': 2},
                    {'name': 'Aso Ebi, Iro & Buba', 'description': 'Traditional ceremonial attire, lace Aso Ebi, and luxury cultural garments.', 'display_order': 3},
                    {'name': 'Boubous & Rich Auntie Gowns', 'description': 'Flowing silk, chiffon, damask boubous, and rich auntie dresses.', 'display_order': 4},
                    {'name': 'Corset Gowns & Evening Dresses', 'description': 'African print dresses, structured corset gowns, and ready-to-wear.', 'display_order': 5},
                    {'name': 'Jumpsuits & Playsuits', 'description': 'Tailored Ankara and crepe jumpsuits and modern one-piece outfits.', 'display_order': 6},
                    {'name': 'Women\'s Streetwear & Co-ords', 'description': 'Modern Nigerian streetwear, kimonos, lounge sets, and crop sets.', 'display_order': 7},
                ]
            },
            {
                'name': 'Traditional & Heritage',
                'description': 'Handwoven heritage garments, royal regalia, and ceremonial wear.',
                'display_order': 3,
                'children': [
                    {'name': 'Handwoven Aso Oke', 'description': 'Authentic Yoruba handwoven Aso Oke sets, sashes, and agbadas.', 'display_order': 1},
                    {'name': 'Bridal & Groom Regalia', 'description': 'Complete traditional wedding attire for couples, George wrappers, and beads.', 'display_order': 2},
                    {'name': 'Adire & Batik Heritage', 'description': 'Hand-dyed authentic Abeokuta Adire Eleko, silk and cotton pieces.', 'display_order': 3},
                ]
            },
            {
                'name': 'Accessories',
                'description': 'Traditional caps (Fila), hand-woven sashes, coral beads, geles, and fashion accessories.',
                'display_order': 4,
                'children': [
                    {'name': 'Caps (Fila) & Headwear', 'description': 'Embroidered Fila, Gobi, and traditional caps.', 'display_order': 1},
                    {'name': 'Geles & Auto-Geles', 'description': 'Pre-tied luxury geles, headties, and velvet sashes.', 'display_order': 2},
                    {'name': 'Coral Beads & Jewelry', 'description': 'Traditional Edo/Benin/Igbo/Yoruba coral necklaces and royal accessories.', 'display_order': 3},
                ]
            }
        ]

        created_count = 0
        updated_count = 0
        for cat_info in categories_data:
            children = cat_info.pop('children', [])
            parent_cat = Category.objects.filter(name=cat_info['name']).first()
            if not parent_cat:
                parent_cat = Category.objects.create(**cat_info)
                created_count += 1
            else:
                parent_cat.description = cat_info.get('description', parent_cat.description)
                parent_cat.display_order = cat_info.get('display_order', parent_cat.display_order)
                parent_cat.save(update_fields=['description', 'display_order'])
                updated_count += 1

            for child_info in children:
                child_cat = Category.objects.filter(name=child_info['name']).first()
                if not child_cat:
                    child_cat = Category.objects.create(parent=parent_cat, **child_info)
                    created_count += 1
                else:
                    child_cat.parent = parent_cat
                    child_cat.description = child_info.get('description', child_cat.description)
                    child_cat.display_order = child_info.get('display_order', child_cat.display_order)
                    child_cat.save(update_fields=['parent', 'description', 'display_order'])
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded category tree ({created_count} created, {updated_count} updated)."))
