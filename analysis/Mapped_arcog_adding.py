#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector as mc
import argparse
import csv
import re
from configurations import config
from pathlib import Path
import requests
import time

################################################################################################
parser = argparse.ArgumentParser(description='Add mapped arcogs to database and remove previous results')
parser.add_argument('--database', '-b', type=str, help="database to connect to")
parser.add_argument('--table', '-t',  type=str, help="the name you want to give to your table")
parser.add_argument('--type', '-y', type=str, default='regular',
                    help="mapper if your arcog file comes from eggnog mapper, regular if the file only contains the "
                         "name of the organisme and the name of the sequence")
parser.add_argument('--arcogs', '-a', type=str, required=False, help="your arcog file")
parser.add_argument('--helicasefile', '-f', type=str, required=False,
                    help="tsv file with CGBD id associated to uniprot protein id ")

parser.add_argument('--drop', '-d', required=False, action="store_true", help='drop all tables')
parser.add_argument('--name', '-n', type=str, required=False, default='obsolete',
                    help='filename of obsolete uniprot id (default obsolete.txt)')
args = parser.parse_args()
################################################################################################

rootpath = Path(__file__).resolve().parent.parent

try:
    # try connection the database
    conn = mc.connect(host='localhost',
                      database=args.database,
                      user=config.BD_USER,  # BD_USER by default in directroy configurations
                      password=config.BD_PASSWORD)  # BD_PASSEWORD by default in directory configurations

except mc.Error as err:
    print(err)

else:
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {args.database}")
    cursor.execute(f"USE {args.database}")

    if args.drop:
        cursor.execute(f"DROP TABLE IF EXISTS `proteins_cog_{args.table}`")
        cursor.execute(f"DROP VIEW IF EXISTS `paralogy_{args.table}`")
        cursor.execute(f"DROP VIEW IF EXISTS `multiple_status_{args.table}`")
        cursor.execute(f"DROP TABLE IF EXISTS `strain_proteins_{args.table}`")

    if args.type == 'mapper':
        cursor.execute(f"CREATE TABLE IF NOT EXISTS `proteins_cog_{args.table}`(`id_uniprot` VARCHAR(30), `id_cog` "
                       f"VARCHAR(30), `e_value` FLOAT, `taxon_id` VARCHAR(30), `taxon_name` VARCHAR(100), "
                       f"`max_annotation_level` VARCHAR(100), `category` VARCHAR(5), `go` TEXT, "
                       f"PRIMARY KEY(`id_uniprot`, `id_cog`, `taxon_id`));")
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS `strain_proteins_{args.table}`(`strain` VARCHAR(30), `id_uniprot` "
            f"VARCHAR(30), `sequence` TEXT, PRIMARY KEY(`id_uniprot`));")
        with open(args.arcogs, "r") as fh:
            tsv_emapper = csv.reader(fh, delimiter="\t")
            motif = re.compile(r"(arC.*@2157)")
            for line in tsv_emapper:
                if re.search("^[A-Z]", line[0]):  # and float(line[2]) < 0.05:  # Skip first lines and lines where
                    # e_value < 0.05
                    id_uniprot = line[0]
                    e_value = line[2]
                    category = line[6]
                    go = line[9]

                    for el in line[4].split(","):
                        id_cog_mapper = re.search(".*@", el).group(0)[:-1]
                        taxon_id = re.search("@.*\|", el).group(0)[1:][:-1]
                        taxon_name = el.split("|")[1]
                        max_annotation_level = line[5].split("|")[0]
                        if max_annotation_level == taxon_id:
                            max_annotation_level = "true"
                        else:
                            max_annotation_level = "false"
                        if go == "-":
                            cursor.execute(f"INSERT IGNORE INTO proteins_cog_{args.table} (id_uniprot, id_cog, e_value,"
                                           f" taxon_id, taxon_name, max_annotation_level, category, go) "
                                           f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (id_uniprot, id_cog_mapper, e_value,
                                                                                 taxon_id, taxon_name,
                                                                                 max_annotation_level, category, 'NA'))
                        else:
                            cursor.execute(f"INSERT IGNORE INTO proteins_cog_{args.table} (id_uniprot, id_cog, e_value,"
                                           f" taxon_id, taxon_name, max_annotation_level, category, go) "
                                           f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (id_uniprot, id_cog_mapper, e_value,
                                                                                 taxon_id, taxon_name,
                                                                                 max_annotation_level, category, go))

    if args.type == 'regular':
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS `proteins_cog_{args.table}`(`id_uniprot` VARCHAR(30),`id_cog` VARCHAR(100),"
            f"PRIMARY KEY(`id_uniprot`, `id_cog`));")
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS `strain_proteins_{args.table}`(`strain` VARCHAR(30), `id_uniprot` "
            f"VARCHAR(30), `sequence` TEXT, PRIMARY KEY(`id_uniprot`));")

        with open(args.helicasefile, "r") as fh:  # reading tsv entry file using args module
            tsv_helicases = csv.reader(fh, delimiter="\t")
            obsolete = []
            for line in tsv_helicases:  # File with uniprot id and CBI id
                print(line[1])
                id_uniprot = line[1]
                # Arcogs retrieval
                arcogs = []
                url_arcog = "https://www.uniprot.org/uniprot/" + id_uniprot + ".txt"
                arcog_response = None
                while arcog_response is None:  # retry if exception occurs
                    try:
                        arcog_response = requests.get(url_arcog)
                        arcog_response.raise_for_status()  # If the response was successful, no Exception will be raised

                    except Exception as err:
                        print(f'An error occurred: {err}')  # Python 3.6
                        print("retrying")
                        time.sleep(1)
                        arcog_response = None

                Embl_file = arcog_response.text.split("\n")
                if arcog_response.text == "":  # Unfortunately if obsolete do not return error but empty file
                    obsolete.append(id_uniprot)

                else:
                    for line_arc in Embl_file:  # file
                        if line_arc.startswith("DR   eggNOG"):
                            arcog = line_arc.split("; ")
                            arcogs.append(arcog[1])
                    if arcogs:
                        for el in arcogs:
                            cursor.execute(f"INSERT IGNORE INTO proteins_cog_{args.table} "
                                           f"(id_uniprot, id_cog) VALUES (%s,%s)", (id_uniprot, el))
                        conn.commit()
                    else:
                        cursor.execute(f"INSERT IGNORE INTO proteins_cog_{args.table} "
                                       f"(id_uniprot, id_cog) VALUES (%s,%s)", (id_uniprot, 'NA'))
                        conn.commit()

                        # Instertion for proteins with no cog
                        # Since NULL is not authorized as primary key, string 'NA' is used

                    # sequence retrieval
                    # Strain retrieval
                    strain = line[0].split(".")
                    strain = strain[0][0:5]
                    url_seq = "https://www.uniprot.org/uniprot/" + id_uniprot + ".fasta"
                    seq_response = None

                    while seq_response is None:  # retry if exception occurs
                        try:
                            seq_response = requests.get(url_seq)
                            seq_response.raise_for_status()  # If the response was successful,
                            # no Exception will be raised

                        except Exception as err:
                            print(f'An error occurred: {err}')
                            print("retrying")
                            # Python 3.6
                            time.sleep(1)
                            seq_response = None

                    fasta = seq_response.text
                    if fasta != '':
                        fasta = fasta.split("\n", 1)
                        seq = fasta[1].replace("\n", '')
                        cursor.execute(f"INSERT IGNORE INTO strain_proteins_{args.table} (strain, id_uniprot, sequence)"
                                       f" VALUES (%s,%s,%s)", (strain, id_uniprot, seq))
                        conn.commit()
                    else:
                        cursor.execute(f"INSERT INGORE INTO strain_proteins_{args.table} (strain, id_uniprot, sequence)"
                                       f" VALUES (%s,%s,%s)", (strain, id_uniprot, None))
                        conn.commit()

        obsolete_path = rootpath / f"analysis/results/{args.name}.txt"
        obsolete_file = open(obsolete_path, "w")
        for proteins in obsolete:
            obsolete_file.write(proteins + "\n")
        obsolete_file.close()

        conn.commit()
    # Views
    cursor.execute(
        f"CREATE VIEW multiple_status_{args.table} AS SELECT id_uniprot, count(*) AS multiple "
        f"FROM proteins_cog_{args.table} GROUP BY id_uniprot;")  # Proteins with multiple cogs associated
    conn.commit()

    cursor.execute(f"CREATE VIEW paralogy_{args.table} AS SELECT id_cog, count(strain) AS strain_count, "
                   f"count(id_uniprot) as proteins_count FROM proteins_cog_{args.table} NATURAL JOIN "
                   f"strain_proteins GROUP BY id_cog;")
    conn.commit()

    # strain and protein cog by cog

    if conn.is_connected():
        cursor.close()  # close cursor
        conn.close()  # close connection
