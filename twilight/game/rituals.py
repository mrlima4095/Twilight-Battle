"""Verificação e execução de rituais."""

class RitualManager:
    @staticmethod
    def check_ritual_157(game, caster_id):
        """Verifica condições do Ritual 157 - Requer Apofis, Mago Negro, 6 zumbis e 2 elfos em modo de defesa"""
        player = game.player_data[caster_id]
        
        # Verificar se tem Apofis em campo (ataque ou defesa)
        has_apofis = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'apofis':
                has_apofis = True
                break
        
        if not has_apofis:
            return False, "Requer Apofis em campo"
        
        # Verificar se tem Mago Negro em campo
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        if not has_mago_negro:
            return False, "Requer Mago Negro em campo"
        
        # Contar zumbis em campo (qualquer posição)
        zumbis_count = 0
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'zumbi':
                zumbis_count += 1
        
        if zumbis_count < 6:
            return False, f"Requer 6 zumbis em campo (tem {zumbis_count})"
        
        # Contar elfos em MODO DE DEFESA
        elfos_defesa = 0
        for card in player['defense_bases']:
            if card and card['id'] == 'elfo':
                elfos_defesa += 1
        
        if elfos_defesa < 2:
            return False, f"Requer 2 elfos em modo de defesa (tem {elfos_defesa})"
        
        return True, "Ritual 157 pode ser realizado"
    @staticmethod
    def execute_ritual_157(game, caster_id, target_player_id):
        """Executa o Ritual 157 - Rouba todos os talismãs do alvo"""
        caster = game.player_data[caster_id]
        target = game.player_data[target_player_id]
        
        # Coletar todos os talismãs do alvo
        stolen_talismans = []
        for talisman in target['talismans']:
            stolen_talismans.append(talisman)
        
        # Remover talismãs do alvo
        target['talismans'] = []
        
        # Adicionar talismãs ao conjurador
        caster['talismans'].extend(stolen_talismans)
        
        return {
            'success': True,
            'message': f"Ritual 157 realizado! {len(stolen_talismans)} talismãs roubados de {target['name']}",
            'stolen_count': len(stolen_talismans)
        }
    
    @staticmethod
    def check_ritual_amor(game, caster_id):
        """Verifica condições do Ritual Amor - Requer Ninfa Belly Lorem e Vampiro Necrothic Tayler"""
        player = game.player_data[caster_id]
        
        # Verificar se tem Ninfa Lorem em campo
        has_ninfa = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'ninfa':
                has_ninfa = True
                break
        
        if not has_ninfa:
            return False, "Requer Ninfa Belly Lorem em campo"
        
        # Verificar se tem Vampiro Necrothic Tayler em campo
        has_vampiro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'vampiro_tayler':
                has_vampiro = True
                break
        
        if not has_vampiro:
            return False, "Requer Vampiro Necrothic Tayler em campo"
        
        return True, "Ritual Amor pode ser realizado"
    @staticmethod
    def execute_ritual_amor(game, caster_id, target_player_id):
        """Executa o Ritual Amor - Anula a maldição do Profeta"""
        target = game.player_data[target_player_id]
        
        # Remover profecia do alvo se existir
        if target.get('profecia_alvo'):
            target['profecia_alvo'] = None
            target['profecia_rodadas'] = 0
        
        # Remover efeitos de maldição
        target['active_effects'] = [effect for effect in target['active_effects'] 
                                   if effect.get('type') != 'profecia_morte']
        
        return {
            'success': True,
            'message': f"Ritual Amor realizado! Maldição anulada para {target['name']}"
        }
    
    @staticmethod
    def get_available_rituals(game, player_id):
        """Retorna lista de rituais disponíveis baseado nas condições"""
        player = game.player_data[player_id]
        available_rituals = []
        
        # Verificar se tem carta do ritual na mão (para magos comuns)
        rituals_in_hand = [card for card in player['hand'] if card.get('type') == 'ritual']
        
        # Verificar se tem Mago Negro em campo (pode realizar qualquer ritual)
        has_mago_negro = False
        for card in player['attack_bases'] + player['defense_bases']:
            if card and card['id'] == 'mago_negro':
                has_mago_negro = True
                break
        
        # Lista de rituais disponíveis
        ritual_list = [
            {'id': 'ritual_157', 'name': 'Ritual 157', 'description': 'Rouba todos os talismãs de um jogador'},
            {'id': 'ritual_amor', 'name': 'Ritual Amor', 'description': 'Anula a maldição do Profeta'}
        ]
        
        for ritual in ritual_list:
            # Verificar se pode realizar (tem a carta ou é Mago Negro)
            has_card = any(card['id'] == ritual['id'] for card in rituals_in_hand)
            
            if has_card or has_mago_negro:
                # Verificar condições específicas
                if ritual['id'] == 'ritual_157':
                    can_cast, message = RitualManager.check_ritual_157(game, player_id)
                    if can_cast:
                        ritual['conditions_met'] = True
                        ritual['message'] = '✅ Condições atendidas'
                    else:
                        ritual['conditions_met'] = False
                        ritual['message'] = f'❌ {message}'
                
                elif ritual['id'] == 'ritual_amor':
                    can_cast, message = RitualManager.check_ritual_amor(game, player_id)
                    if can_cast:
                        ritual['conditions_met'] = True
                        ritual['message'] = '✅ Condições atendidas'
                    else:
                        ritual['conditions_met'] = False
                        ritual['message'] = f'❌ {message}'
                
                available_rituals.append(ritual)
        

