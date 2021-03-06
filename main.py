# coding=UTF-8
import os
import argparse
from tqdm import tqdm
import torch
#import pdb
import random
import pickle
import numpy as np

from transformers import BertTokenizer, BertModel, BertConfig, BertForMaskedLM
from transformers import AutoTokenizer, AutoModel, AutoConfig, AlbertForMaskedLM
from models import ProtSiam, ProtVanilla
from trainer import Trainer
from utils import *

if __name__ == '__main__':

	parser = argparse.ArgumentParser()
	parser.add_argument('--seed', type=int, default=42)
	parser.add_argument('--bert_lr', type=float, default=1e-5)
	parser.add_argument('--model_lr', type=float, default=1e-3)
	parser.add_argument('--batch_size', type=int, default=1)
	parser.add_argument('--epoch', type=int, default=1000)
	parser.add_argument('--no_use_gpu', action='store_true', default=False)
	parser.add_argument('--weight_decay', type=float, default=1e-7)
	parser.add_argument('--load_path', type=str, default=None)
	parser.add_argument('--data', type=str, default='PB16IC', choices = ['PB16I', 'PB16IC', 'WDTaxo', 'WNTaxo', 'CN-PBI', 'CN-PBIC']) 
	parser.add_argument('--plm', type=str, default='bert', choices = ['bert', 'bert_tiny', 'bert_mini', 'bert_small'])
	parser.add_argument('--model', type=str, default='psn', choices= ['prot_vanilla', 'psn'])
	parser.add_argument('--ent_per_con', type=int, default=4, help='eta, each triple samples at most 2*eta instances')
	parser.add_argument('--typicalness', type=str, default='none', choices = ['none']) 
	parser.add_argument('--add_reverse_label', default=False, action = 'store_true', help='transformer binary classification to trinary classification: x_isA_y, y_isA_x or not related')
	#parser.add_argument('--language', type=str, default='en', choices = ['zh', 'en'])
	parser.add_argument('--con_desc', default=False, action = 'store_true', help = 'use description of concept') 
	parser.add_argument('--use_probase_text', default=False, action = 'store_true')
	parser.add_argument('--train_instance_of', default=False, action = 'store_true')
	parser.add_argument('--load_epoch', type=int, default=-1)
	parser.add_argument('--load_metric', type=str, default='subclass_acc')
	parser.add_argument('--variant', type=str, default='default', choices= ['default', 'selfatt', 'hybrid'])
	parser.add_argument('--use_cls_token', default=False, action = 'store_true')
	parser.add_argument('--type_constrain', default=False, action = 'store_true')
	parser.add_argument('--test_link_prediction', default=False, action= 'store_true')
	parser.add_argument('--test_triple_classification', default=False, action= 'store_true')
	parser.add_argument('--freeze_plm', default=False, action= 'store_true')
	parser.add_argument('--separate_classifier', default=False, action= 'store_true')
	parser.add_argument('--train_MLM', default=False, action= 'store_true')
	parser.add_argument('--distance_metric', default=False, action='store_true')

	arg = parser.parse_args()

	if arg.freeze_plm:
		arg.use_cls_token = True

	random.seed(arg.seed)
	np.random.seed(arg.seed)
	torch.manual_seed(arg.seed)

	if arg.no_use_gpu == False:
		device = torch.device('cuda')
	else:
		device = torch.device('cpu')

	if arg.data in ['CN-PBI', 'CN-PBIC']:
		arg.language = 'zh'
	else:
		arg.language = 'en'


	data_path = './data/{0}'.format(arg.data)
	data_bundle = load_data(data_path)


	identifier = '{}_{}'.format(arg.language, arg.data)

	print('Data path: ', data_path)

	if arg.language == 'zh':
		bert_pretrained = 'voidful/albert_chinese_tiny'
	elif arg.plm == 'bert':
		bert_pretrained = "bert-base-uncased"
	elif arg.plm == 'bert_tiny':
		bert_pretrained = "prajjwal1/bert-tiny"
	elif arg.plm == 'bert_mini':
		bert_pretrained = "prajjwal1/bert-mini"
	elif arg.plm == 'bert_small':
		bert_pretrained = "prajjwal1/bert-small"

	if arg.add_reverse_label:
		num_labels = 3
	else:
		num_labels = 2

	config = AutoConfig.from_pretrained(bert_pretrained, num_labels=num_labels)
	tokenizer = AutoTokenizer.from_pretrained(bert_pretrained)
	bertmodel = AutoModel.from_pretrained(bert_pretrained)
	

	if arg.train_MLM:
		bertMLMcls = BertForMaskedLM(bertmodel.config).cls
	else:
		bertMLMcls = None

	trainable_models = ['psn', 'prot_vanilla']
	if arg.model in trainable_models:

		if arg.model == 'psn':
			model = ProtSiam(bertmodel, arg.ent_per_con, data_bundle['concept_instance_info'].keys(), arg.train_instance_of, arg.freeze_plm, len(data_bundle['concepts']), 
				len(data_bundle['instances']),num_labels, arg.separate_classifier, arg.train_MLM, arg.distance_metric, bertMLMcls = bertMLMcls, use_cls_token = arg.use_cls_token)
		elif arg.model == 'prot_vanilla':
			model = ProtVanilla(bertmodel, arg.ent_per_con, arg.train_instance_of, arg.freeze_plm, len(data_bundle['concepts']), len(data_bundle['instances']) , 
				num_labels, arg.separate_classifier, arg.train_MLM, arg.distance_metric, bertMLMcls = bertMLMcls)

		no_decay = ["bias", "LayerNorm.weight"]

		param_group = [
			{'lr': arg.model_lr, 'params': [p for n, p in model.named_parameters()
										   if ('bert' not in n) and
										   (not any(nd in n for nd in no_decay))],
			 'weight_decay': arg.weight_decay},
			{'lr': arg.model_lr, 'params': [p for n, p in model.named_parameters()
										   if ('bert' not in n) and
										   (any(nd in n for nd in no_decay))],
			 'weight_decay': 0.0},
		]	

		if not arg.freeze_plm:
			param_group += [
				{'lr': arg.bert_lr, 'params': [p for n, p in model.named_parameters()
											   if ('bert' in n) and
											   (not any(nd in n for nd in no_decay)) ], 
				 'weight_decay': arg.weight_decay},
				{'lr': arg.bert_lr, 'params': [p for n, p in model.named_parameters()
											   if ('bert' in n) and
											   (any(nd in n for nd in no_decay))],
				 'weight_decay': 0.0},
			]

		optimizer = torch.optim.AdamW(param_group)

	hyperparams = {
		'data': arg.data, 
		'bert_lr': arg.bert_lr,
		'model_lr': arg.model_lr,
		'batch_size': arg.batch_size,
		'epoch': arg.epoch,
		'model_name': arg.model,
		'ent_per_con': arg.ent_per_con,
		'typicalness': arg.typicalness,
		'identifier': identifier,
		'con_desc': arg.con_desc,
		'load_path': arg.load_path,
		'use_probase_text': arg.use_probase_text,
		'evaluate_every': 1, 
		'update_every': 1,
		'add_reverse_label': arg.add_reverse_label,
		'language': arg.language,
		'variant': arg.variant,
		'train_instance_of': arg.train_instance_of,
		'num_labels': num_labels,
		'load_epoch': arg.load_epoch,
		'load_metric': arg.load_metric,
		'use_cls_token': arg.use_cls_token,
		'freeze_plm': arg.freeze_plm,
		'plm': arg.plm,
		'type_constrain': arg.type_constrain,
		'separate_classifier': arg.separate_classifier,
		'train_MLM': arg.train_MLM,
		'distance_metric': arg.distance_metric
	}
	trainer = Trainer(data_bundle, model, tokenizer, optimizer, device, hyperparams)



	if arg.test_link_prediction:
		# directly perform link prediction
		trainer.link_prediction(epc=-1, valid = False)
	elif arg.test_triple_classification:
		trainer.test_triple_classification(epc=-1, valid = False) #True
	else:
		# train, and perform test (accuracy) / test (link prediction)
		trainer.run()


