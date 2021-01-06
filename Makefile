#ODIR=/mnt/nas_swe/Clients/Energimmo/0.\ Admin/Facturation/Factures\ clients/Automatique
ODIR=/dev/shm/ch.energimmo

run: build
	docker run -it --rm=true -v $(ODIR):/out egmo_facturation

build:
	docker build -t egmo_facturation .
