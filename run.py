#!/usr/bin/env python3
# -*- coding: utf-8 -*-
## Frank@Villaro-Dixon.eu - DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE, etc.

import sys
import traceback
import csv
import os
import yaml
import pandas as pd
import config
import datetime
from dateutil.relativedelta import relativedelta
import calendar
import jinja2
import time
import shutil
import pdfkit
import uuid
pd.set_option('display.max_rows', 2)

today = datetime.date.today()
d = today - relativedelta(months=1)
last_month_start = datetime.date(d.year, d.month, 1)
(_, days_month) = calendar.monthrange(d.year, d.month)

date_from = datetime.datetime(last_month_start.year, last_month_start.month, last_month_start.day)
date_to = datetime.datetime(last_month_start.year, last_month_start.month, days_month, 23, 59)
assert(date_to-date_from < datetime.timedelta(days=32))
assert(date_to-date_from > datetime.timedelta(days=28))

invoice_dates = {
    'from': date_from,
    'to': date_to,
}

gen_invoice_on = None
if True:
    gen_invoice_on = date_to+relativedelta(days=2)
    while gen_invoice_on.weekday() >= 5:
        gen_invoice_on += relativedelta(days=1)

print(invoice_dates)


def get_load_curve(MPAN_id, MPAN, date_from, date_to): #{{{
    serie = None
    for tries in range(25):
        try:
            print(config.api_endpoint.format(MPAN_id))
            serie = pd.read_json(config.api_endpoint.format(MPAN_id), 'records', 'series')
        except:
            time.sleep(tries*2)
            continue
        if serie is not None:
            break

    if serie is None:
        print(config.api_endpoint.format(MPAN_id))
        print(MPAN_id)
        raise Exception('Could not fetch data')

    print('WILL DO {}'.format(MPAN))
    print('From {} to {}'.format(date_from, date_to))

    serie = serie.rename(MPAN)
    wanted = serie.truncate(date_from, date_to)
    wanted = wanted.resample('15T').asfreq()

    if wanted.isnull().values.any():
        print('Serie {} has null values !!!'.format(MPAN))
        raise Exception('Serie {} has null values !!!'.format(MPAN))

    firsti = wanted.index[0]
    lasti = wanted.index[-1]
    totsec = (lasti-firsti).total_seconds()
    tot15mins = int(totsec/(60*15))+1
    numbins = len(wanted.index)

    indexerror = abs((numbins-tot15mins)/tot15mins)*100
    if indexerror > 1/100: #More than 1% of missing bins:
        print('Ixerror')
        print(wanted.index[wanted.isnull()])

        print(firsti)
        print(lasti)
        print(tot15mins)
        print(numbins)
        raise Exception('Missing data: {} ({} instead of {} 15mins bins)'.format(indexerror, numbins, tot15mins))

    secs_from_index_to_eomonth = abs((lasti-date_to).total_seconds())
    if secs_from_index_to_eomonth > (15*60*4)*3: #More than 1h offset
        raise Exception('Last index is {} instead of {}'.format(lasti, date_to))

    secs_from_index_to_smonth = abs((firsti-date_from).total_seconds())
    if secs_from_index_to_smonth > (15*60*4)*3: #More than 1h offset
        raise Exception('First index is {} instead of {}'.format(firsti, date_from))

    return wanted
#}}}
def get_load_curve_egmo(MPAN_id, date_from, date_to): #{{{
    serie = None
    for tries in range(5):
        try:
            print(config.api_endpoint.format(MPAN_id))
            serie = pd.read_json(config.api_endpoint.format(MPAN_id), 'records', 'series')
        except:
            continue
        if serie is not None:
            break

    if serie is None:
        print(config.api_endpoint.format(MPAN_id))
        print(MPAN_id)
        raise Exception('Could not fetch data')

    print('WILL DO {}'.format(MPAN_id))
    print('From {} to {}'.format(date_from, date_to))

    serie = serie.rename(MPAN_id)
    wanted = serie.truncate(date_from-datetime.timedelta(minutes=15), date_to)
    wanted = wanted.resample('15T')
    wanted = wanted.diff()

    firsti = wanted.index[0]
    lasti = wanted.index[-1]
    totsec = (lasti-firsti).total_seconds()
    tot15mins = int(totsec/(60*15))+1

    wanted_secs = (date_to-date_from).total_seconds()

    if abs(wanted_secs-totsec) > datetime.timedelta(hours=21).total_seconds():
        #raise Exception(f'{MPAN_id} goes from {firsti} to {lasti}. Missing time')
        raise Exception()

    return wanted
#}}}
def get_meters(contract, date_from, date_to): #{{{

        energy_price = float(contract['energy_price'])

        meters = []
        for meter in contract['meters']:
            if meter['MPAN'].startswith('egmo'):
                load_curve = get_load_curve_egmo(meter['MPAN'], date_from, date_to)
            else:
                load_curve = get_load_curve(meter['MPAN']+'A', meter['MPAN'], date_from, date_to)

            volume = load_curve.sum(skipna=True)

            meters.append({
                'MPAN': meter['MPAN'],
                'name': meter['name'],
                'price_kWh': energy_price,
                'price_volume': round(volume * energy_price/100, 1),
                'volume': volume,
                'load_curve': load_curve,
            })

        return sorted(meters, key=lambda x: x['name'])
#}}}
def generate_invoice(main_config, contract, invoice_dates): #{{{
    meters = get_meters(contract, invoice_dates['from'], invoice_dates['to'])

    all_params = main_config.copy()
    all_params['meters'] = meters

    total_price = 0
    total_kWh = 0

    for meter in meters:
        total_price += meter['price_volume']
        total_kWh += meter['volume']
    
    all_params['total_price'] = total_price
    all_params['total_volume'] = total_kWh

    tax_rate = config.tax_rate
    if 'tax_rate' in main_config: #For specific contracts like international orgs.
        tax_rate = float(main_config['tax_rate'])
    tax_rate /= 100

    all_params['tax_price'] = round(total_price * tax_rate, 1)
    all_params['tax_rate'] = tax_rate * 100
    all_params['total_price_w_tax'] = round(total_price * (1+tax_rate), 1)



    global gen_invoice_on
    if gen_invoice_on:
        invoice_gen_date = gen_invoice_on
    else:
        invoice_gen_date = time.gmtime()

    invoice_gen_date_Ymd = time.strftime("%Y%m%d", invoice_gen_date.timetuple())
    invoice_date_Y_m = time.strftime("%Y-%m", invoice_dates['from'].timetuple())

    invoice_number = '{}-{}-{}'.format(main_config['invoice_prefix'], invoice_gen_date_Ymd, str(uuid.uuid4())[0:4])

    all_params['invoice_number'] = invoice_number

    creation_date = time.strftime("%d TT %Y", invoice_gen_date.timetuple())
    month = int(time.strftime("%m", invoice_gen_date.timetuple()))
    human_month = {
            1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
            5: 'mai', 6: 'juin', 7: 'juillet', 8: 'aout',
            9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'}
    creation_date = creation_date.replace('TT', human_month[month]) #UGLY


    all_params['creation_date'] = creation_date
    all_params['creation_date_jjmmaaaa'] = time.strftime("%d.%m.%Y", invoice_gen_date.timetuple())

    print('Hello')
    all_params['start_invoice_date'] = invoice_dates['from']
    print('Goodbye')
    all_params['end_invoice_date'] = invoice_dates['to']
    all_params['contract_address'] = contract['address']
    all_params['energy_quality'] = contract['energy_quality']
    all_params['energy_price'] = contract['energy_price']
    #all_params['egmo_debit_id'] = all_params.get('egmo_debit_id', 'N/A')
    #all_params['egmo_credit_id'] = all_params['egmo_credit_id']

    libelle_client = all_params['name']
    libelle_site = contract['address']
    libelle_periode = invoice_dates['from']
    all_params['egmo_libelle'] =  '{} — {} — {}'.format(libelle_client, libelle_site, invoice_date_Y_m)

    if 'your_ref' in contract:
        all_params['your_ref'] = contract['your_ref']



    opath = os.path.join(config.invoices_output_dir, main_config['invoice_prefix'])
    if not os.path.isdir(opath):
        os.makedirs(opath)

    address_without_spaces = contract['address'].replace(' ', '_')
    fname = '{}.{}'.format(invoice_dates['from'].strftime("%Y-%m"), address_without_spaces)
    ofile_prefix = os.path.join(opath, fname)



    html = generate_invoice_html(all_params)
    if 'sending_address' in main_config:
        sending_header_html = get_sending_header(all_params)
    else:
        sending_header_html = False
    generate_pdf(html, ofile_prefix+'.pdf', sending_header_html)

    generate_csv(meters, ofile_prefix+'.csv')
    return all_params
#}}}
def generate_invoice_html(invoice_content): #{{{
    templateLoader = jinja2.FileSystemLoader(searchpath="./")
    environment = jinja2.Environment(loader=templateLoader)

    def spaceize(number):
        #fuck everybody
        return '{:,}'.format(number).replace(',', ' ')

    environment.filters['spaceize'] = spaceize

    template = environment.get_template(config.template_file)
    html = template.render(invoice_content)
    return html
#}}}
def get_sending_header(main_config): #{{{
    templateLoader = jinja2.FileSystemLoader(searchpath="./")
    environment = jinja2.Environment(loader=templateLoader)

    template = environment.get_template(config.template_file_sending_header)

    html = template.render(main_config)
    return html
#}}}
def generate_pdf(html, ofile, sending_header_html): #{{{
    if not os.path.isdir(config.tmp_path):
        os.makedirs(config.tmp_path)

    try:
        shutil.copytree('files', config.tmp_path+'/files')
    except:
        pass

    tmp_html = config.tmp_path+'/tmp.html'
    with open(tmp_html, 'w') as f:
        f.write(html)

    opt = {
        '--print-media-type': '',
        '--background': '',
    }

    if sending_header_html:
        tmp_html_header = config.tmp_path+'/tmp_header.html'
        with open(tmp_html_header, 'w') as f:
            f.write(sending_header_html)
        pdfkit.from_file([tmp_html_header, tmp_html], ofile, options=opt)
    else:
        pdfkit.from_file(tmp_html, ofile, options=opt)
#}}}
def generate_csv(meters, ofile): #{{{
    meters_s = []
    for m in meters:
        meters_s.append(m['load_curve'])

    df = pd.concat(meters_s, axis=1)
    df.to_csv(ofile)
#}}}


def process_client(client_dir, invoice_dates): #{{{
    main_config_file = os.path.join(client_dir, 'config.yaml')
    main_config = yaml.load(open(main_config_file))
    client_invoices_data = []

    for contract_file in os.listdir(client_dir):
        if 'config.yaml' in contract_file:
            continue
        if '.swp' in contract_file:
            continue

        cpath = os.path.join(client_dir, contract_file)
        contract = yaml.load(open(cpath))

        try:
            invoice_data = generate_invoice(main_config, contract, invoice_dates)
            client_invoices_data.append(invoice_data)

        except Exception as e:
            #raise
            with open('/out/logfile.log', 'a') as f:
                f.write('Could not do {} for {}\n'.format(contract_file, invoice_dates))
            print('>>>>>>>> Could not {}'.format(contract_file))
            print(e)
            traceback.print_exc()
    return client_invoices_data

#}}}
def process_all_clients(invoice_dates): #{{{
    all_invoices_data = []
    #for client_dir in ['SWE']: #os.listdir(config.client_base_dir):
    #for client_dir in ['PIG32', 'TURI']:
    for client_dir in os.listdir(config.client_base_dir):
        client_dir_path = os.path.join(config.client_base_dir, client_dir)
        invoices_data = process_client(client_dir_path, invoice_dates)
        all_invoices_data += invoices_data
    return all_invoices_data
#}}}



def write_csv(invoices_data):  #{{{
    fields = [
        ('Date de la facture', 'creation_date_jjmmaaaa'),
        ('N° de pièce', True, ''),
        ('Libellé', 'egmo_libelle'),
        ('Débit', 'egmo_debit_id'),
        ('Crédit', 'egmo_credit_id'),
        ('Montant TTC', 'total_price_w_tax'),
        ('Journal', True, 'v'),
        ('ME-montant', True, ''),
        ('ME-cours', True, ''),
        ('TVA-taux', 'tax_rate'),
        ('TVA-montant', 'tax_price'),
        ('TVA-compte', True, 'c'),
        ('TVA-type', True, '2'),
        ('TVA-méthode', True, '2'),
        ('TVA-part-soumise', True, '100%'),
        ('ME-code', True, ''),
        ('ME-qté', True, ''),
        ('commentaires', True, ''),
        ('analytique', True, ''),
        ('TVA-code', True, ''),


    ]

    fcsv = '/out/factures.{}.{}.csv'.format(date_from.year, date_from.month)
    with open(fcsv, 'w', encoding='utf-8') as csvfile:
        sw = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
        header = [x[0] for x in fields]
        sw.writerow([";".join(header)])

        for invoice in invoices_data:
            if 'SWE' in invoice['name']:
                continue

            to_write = []
            for field_row in fields:
                rowtype = field_row[1]
                if rowtype == True:
                    value = field_row[2]
                else:
                    try:
                        value = invoice[field_row[1]]
                    except:
                        value = 'N/A'
                to_write.append(str(value))
            sw.writerow([";".join(to_write)])

#}}}

invoices_data = process_all_clients(invoice_dates)
write_csv(invoices_data)




# vim: set ts=4 sw=4 et:

