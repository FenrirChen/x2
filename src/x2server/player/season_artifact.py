"""Official five-slot erosion: paid preview, explicit save/delete, season scope."""
from collections import Counter
from importlib.resources import files
import json
import secrets

from .economy import UnresolvedEconomy
from .battle_bonuses import f32
from x2server.messages.season import encode


class SeasonArtifact:
    def __init__(self, season):
        self.s, self.e, self.store = season, season.e, season.store
        data = json.loads(files('x2server').joinpath('data/season_artifact.json').read_text('utf8'))
        self.slots = {r['ArtifactSlotID'] - 1: r for r in data['slots']}
        self.jewels = {r['JewelID']: r for r in data['jewels']}
        self.fuses = {(r.get('FuseID', 0), r['ProfEnum']): r for r in data['fuses']}

    @staticmethod
    def weighted(values, weights):
        point = secrets.randbelow(sum(weights))
        for value, weight in zip(values, weights):
            if point < weight:
                return value
            point -= weight
        raise ValueError('invalid erosion weights')

    def state_record(self, player, hero):
        if not self.s.active(player) or not hero.get('god_equip'):
            return {}
        row = self.store.db.execute('SELECT state_json FROM season_state WHERE player_id=? AND instance_id=?',
                                    (player, self.s.instance)).fetchone()
        record = json.loads(row[0]).get('artifact_erosion', {}).get(str(hero['id']), {}) if row else {}
        if not isinstance(record, dict) or record.get('artifact_id') != hero['god_equip']['id']:
            return {}
        cleaned = {'artifact_id': record['artifact_id']}
        for namespace in ('saved', 'pending'):
            cleaned[namespace] = {}
            props = record.get(namespace, {})
            if not isinstance(props, dict):
                continue
            for key, prop in props.items():
                if key not in {str(i) for i in self.slots} or not isinstance(prop, dict):
                    continue
                row = self.slots[int(key)]
                if (prop.get('slot') == int(key) and prop.get('attrType') in row['ArtifactEffect']
                        and type(prop.get('attrVal')) is int and prop['attrVal'] in row['ArtifactEffectValue']):
                    cleaned[namespace][key] = prop
        return cleaned

    def view(self, player, hero):
        if not hero.get('god_equip'):
            return hero
        record = self.state_record(player, hero)
        artifact = dict(hero['god_equip'])
        artifact['artifact_properties'] = list(record.get('saved', {}).values())
        artifact['random_artifact_properties'] = list(record.get('pending', {}).values())
        return {**hero, 'god_equip': artifact}

    def attributes(self, player, hero):
        record = self.state_record(player, hero)
        result = Counter()
        for key, prop in record.get('saved', {}).items():
            slot = int(key)
            row = self.slots[slot]
            value = prop['attrVal']
            jewel = self.jewels.get(hero['god_equip'].get('jewels', {}).get(key, 0))
            if jewel:
                star = jewel['StarLevel']
                # Native RefreshDown uses the second bonus for jewel type 99,
                # the first bonus otherwise, multiplying by (1 + bonus * .01).
                bonus = row['JewelEffect2' if jewel['Type']['value'] == 99 else 'JewelEffect1'][star - 1]
                value = int(f32(f32(value) * f32(1 + f32(bonus * f32(.01)))))
            result[prop['attrType']] += value
        return dict(result)

    def operate(self, player, req, token):
        hero_id, slot, op = req.get('heroId'), req.get('slot', 0), req.get('type')
        hero = next((h for h in self.store.get(player)['snapshot'].get('heroes', []) if h['id'] == hero_id), None)
        if not hero or not hero.get('god_equip') or slot not in self.slots or op not in (1, 2, 3):
            raise UnresolvedEconomy('invalid erosion operation or unowned artifact')
        artifact = hero['god_equip']
        from .progression import catalog
        prototype = next((r for r in catalog()['hero_unlock'] if r['hero_id'] == hero_id), None)
        if not prototype:
            raise UnresolvedEconomy('unknown artifact owner')
        if artifact['id'] != prototype['artifact_id']:
            raise UnresolvedEconomy('unexpected artifact identity')
        fuse = self.fuses.get((artifact['star'], prototype['profession']))
        if not fuse or fuse['HoleIsOpen'][slot] != 1:
            raise UnresolvedEconomy('artifact socket is not open')
        state = self.s.state(player)
        records = state.setdefault('artifact_erosion', {})
        record = records.setdefault(str(hero_id), {'artifact_id': artifact['id'], 'saved': {}, 'pending': {}})
        if record['artifact_id'] != artifact['id']:
            raise UnresolvedEconomy('artifact changed')
        key = str(slot)
        if op == 1:
            row = self.slots[slot]
            self.s.spend(player, row['CostItem'], row['CostNum'])
            record['pending'][key] = {'slot': slot,
                'attrType': self.weighted(row['ArtifactEffect'], row['AttribProbability']),
                'attrVal': self.weighted(row['ArtifactEffectValue'], row['ValueProbability'])}
            self.s.write(player, state)
            self.s.event(player, 'erosion:' + token, 98, 0, 1)
        elif op == 2:
            if key not in record['pending']:
                raise UnresolvedEconomy('no erosion preview to save')
            record['saved'][key] = record['pending'].pop(key)
            self.s.write(player, state)
        else:
            # Compatibility policy for the unused OptDelete opcode: discard only the preview.
            if key not in record['pending']:
                raise UnresolvedEconomy('no erosion preview to discard')
            record['pending'].pop(key)
            self.s.write(player, state)
        return {'code': 10, 'type': op}

    def hero_message(self, player):
        from .hero import encode_hero_data
        from x2server.network.dispatcher import OutboundMessage
        return OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': [
            encode_hero_data(h, season=self.s, player_id=player)
            for h in self.store.get(player)['snapshot'].get('heroes', [])]})
